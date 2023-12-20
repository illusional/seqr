from collections import defaultdict
from datetime import datetime, timedelta
from django.db.models import F, Q, Value, CharField, Case, When
from django.db.models.functions import Replace
from django.contrib.postgres.aggregates import ArrayAgg
import json
from typing import Callable, Iterable

from matchmaker.models import MatchmakerSubmission
from reference_data.models import Omim, GENOME_VERSION_LOOKUP
from seqr.models import Family, Individual, Sample, SavedVariant
from seqr.views.utils.airtable_utils import get_airtable_samples
from seqr.utils.gene_utils import get_genes
from seqr.utils.middleware import ErrorsWarningsException
from seqr.utils.search.utils import get_search_samples
from seqr.utils.xpos_utils import get_chrom_pos
from seqr.views.utils.variant_utils import get_variant_main_transcript, get_saved_discovery_variants_by_family, get_sv_name

HISPANIC = 'AMR'
MIDDLE_EASTERN = 'MDE'
OTHER_POPULATION = 'OTH'
ANCESTRY_MAP = {
  'AFR': 'Black or African American',
  HISPANIC: 'Hispanic or Latino',
  'ASJ': 'White',
  'EAS': 'Asian',
  'FIN': 'White',
  MIDDLE_EASTERN: 'Other',
  'NFE': 'White',
  OTHER_POPULATION: 'Other',
  'SAS': 'Asian',
}
ANCESTRY_DETAIL_MAP = {
  'ASJ': 'Ashkenazi Jewish',
  'EAS': 'East Asian',
  'FIN': 'Finnish',
  MIDDLE_EASTERN: 'Middle Eastern',
  'SAS': 'South Asian',
}

MULTIPLE_DATASET_PRODUCTS = {
    'G4L WES + Array v1',
    'G4L WES + Array v2',
    'Standard Exome Plus GWAS Supplement Array',
    'Standard Germline Exome v5 Plus GSA Array',
    'Standard Germline Exome v5 Plus GWAS Supplement Array',
    'Standard Germline Exome v6 Plus GSA Array',
}

SOLVE_STATUS_LOOKUP = {
    **{s: 'Yes' for s in Family.SOLVED_ANALYSIS_STATUSES},
    **{s: 'Likely' for s in Family.STRONG_CANDIDATE_ANALYSIS_STATUSES},
    Family.ANALYSIS_STATUS_PARTIAL_SOLVE: 'Partial',
}

FAMILY_ROW_TYPE = 'family'
SUBJECT_ROW_TYPE = 'subject'
SAMPLE_ROW_TYPE = 'sample'
DISCOVERY_ROW_TYPE = 'discovery'

METADATA_FAMILY_VALUES = {
    'familyGuid': F('guid'),
    'projectGuid': F('project__guid'),
    'analysisStatus': F('analysis_status'),
    'displayName': F('family_id'),
}

METHOD_MAP = {
    Sample.SAMPLE_TYPE_WES: 'SR-ES',
    Sample.SAMPLE_TYPE_WGS: 'SR-GS',
}


def get_family_metadata(projects, additional_fields=None, additional_values=None, format_fields=None, include_metadata=False):
    values = {
        **(METADATA_FAMILY_VALUES if include_metadata else {}),
        **(additional_values or {}),
    }
    family_data = Family.objects.filter(project__in=projects).distinct().values(
        'id', 'family_id', 'project__name', *(additional_fields or []), **values,
    )

    family_data_by_id = {}
    for f in family_data:
        family_id = f.pop('id')
        f.update({
            'project_id': f.pop('project__name'),
            **{k: format(f) for k, format in (format_fields or {}).items()},
        })
        family_data_by_id[family_id] = f

    return family_data_by_id


def parse_anvil_metadata(projects, user, add_row, max_loaded_date=None, omit_airtable=False, include_metadata=False, family_fields=None,
                          get_additional_sample_fields=None, include_discovery_sample_id=False):
    individual_samples = _get_loaded_before_date_project_individual_samples(projects, max_loaded_date) \
        if max_loaded_date else _get_all_project_individual_samples(projects)

    family_values = {
        'pmid_id': Replace('pubmed_ids__0', Value('PMID:'), Value(''), output_field=CharField()),
        'phenotype_description': Replace(
            Replace('coded_phenotype', Value(','), Value(';'), output_field=CharField()),
            Value('\t'), Value(' '),
        ),
        'analysisStatus': METADATA_FAMILY_VALUES['analysisStatus'],
    }
    format_fields = {
        'solve_state': lambda f: get_family_solve_state(f['analysisStatus']),
    }
    if include_metadata:
        family_values['analysis_groups'] = ArrayAgg(
            'analysisgroup__name', distinct=True, filter=Q(analysisgroup__isnull=False))
        format_fields['analysis_groups'] = lambda f: '; '.join(f['analysis_groups'])
    if family_fields:
        family_values.update({k: v['value'] for k, v in family_fields.items()})
        format_fields.update({k: v['format'] for k, v in family_fields.items()})

    family_data_by_id = get_family_metadata(
        projects, additional_fields=['post_discovery_omim_numbers'], additional_values=family_values,
        format_fields=format_fields, include_metadata=include_metadata)

    individuals_by_family_id = defaultdict(list)
    individual_ids_map = {}
    sample_ids = set()
    for individual, sample in individual_samples.items():
        individuals_by_family_id[individual.family_id].append(individual)
        individual_ids_map[individual.id] = (individual.individual_id, individual.guid)
        if sample:
            sample_ids.add(sample.sample_id)

    individual_data_by_family = {
        family_id: _parse_family_individual_affected_data(family_individuals)
        for family_id, family_individuals in individuals_by_family_id.items()
    }

    sample_airtable_metadata = None if omit_airtable else _get_sample_airtable_metadata(list(sample_ids), user)

    saved_variants_by_family = _get_parsed_saved_discovery_variants_by_family(list(family_data_by_id.keys()))

    mim_numbers = set()
    for family in family_data_by_id.values():
        mim_numbers.update(family['post_discovery_omim_numbers'])
    mim_decription_map = {
        o.phenotype_mim_number: o.phenotype_description
        for o in Omim.objects.filter(phenotype_mim_number__in=mim_numbers)
    }

    matchmaker_individuals = set(MatchmakerSubmission.objects.filter(
        individual__in=individual_samples).values_list('individual_id', flat=True)) if include_metadata else set()

    for family_id, family_subject_row in family_data_by_id.items():
        saved_variants = saved_variants_by_family[family_id]

        family_individuals = individuals_by_family_id[family_id]

        mim_numbers = family_subject_row.pop('post_discovery_omim_numbers')
        if mim_numbers:
            family_subject_row.update({
                'disease_id': ';'.join(['OMIM:{}'.format(mim_number) for mim_number in mim_numbers]),
                'disease_description': ';'.join([
                    mim_decription_map.get(mim_number, '') for mim_number in mim_numbers]).replace(',', ';'),
            })

        affected_individual_guids = individual_data_by_family[family_id][0] if family_id in individual_data_by_family else []

        family_consanguinity = any(individual.consanguinity is True for individual in family_individuals)

        family_row = {
            'family_id': family_subject_row['family_id'],
            'consanguinity': 'Present' if family_consanguinity else 'None suspected',
            **family_subject_row,
        }
        if len(affected_individual_guids) > 1:
            family_row['family_history'] = 'Yes'
        add_row(family_row, family_id, FAMILY_ROW_TYPE)

        for individual in family_individuals:
            sample = individual_samples[individual]

            airtable_metadata = None
            has_dbgap_submission = None
            if sample and sample_airtable_metadata is not None:
                airtable_metadata = sample_airtable_metadata.get(sample.sample_id, {})
                dbgap_submission = airtable_metadata.get('dbgap_submission') or set()
                has_dbgap_submission = sample.sample_type in dbgap_submission

            subject_row = _get_subject_row(
                individual, has_dbgap_submission, airtable_metadata, individual_ids_map)
            if individual.id in matchmaker_individuals:
                subject_row['MME'] = 'Yes'
            subject_row.update(family_subject_row)
            add_row(subject_row, family_id, SUBJECT_ROW_TYPE)

            discovery_kwargs = {}
            if sample:
                subject_id = subject_row['subject_id']
                sample_row = _get_sample_row(sample, subject_id, has_dbgap_submission, airtable_metadata, include_metadata, get_additional_sample_fields)
                add_row(sample_row, family_id, SAMPLE_ROW_TYPE)
                if include_discovery_sample_id:
                    discovery_kwargs['sample_id'] = sample.sample_id

            discovery_row = get_genetic_findings_rows(
                saved_variants, individual, participant_id=subject_row['subject_id'],
                post_process_variant=post_process_variant_metadata, **discovery_kwargs)
            add_row(discovery_row, family_id, DISCOVERY_ROW_TYPE)


def get_family_solve_state(analysis_status):
    return SOLVE_STATUS_LOOKUP.get(analysis_status, 'No')


# TODO simplify
def _parse_family_individual_affected_data(family_individuals):
    indiv_id_map = {individual.id: individual.guid for individual in family_individuals}
    return (
        {individual.guid for individual in family_individuals if individual.affected == Individual.AFFECTED_STATUS_AFFECTED},
        {individual.guid for individual in family_individuals if individual.affected == Individual.AFFECTED_STATUS_UNAFFECTED},
        {individual.guid for individual in family_individuals if individual.sex == Individual.SEX_MALE},
        {individual.guid: [
            indiv_id_map[parent_id] for parent_id in [individual.mother_id, individual.father_id]
            if parent_id in indiv_id_map
        ] for individual in family_individuals},
    )


def _get_nested_variant_name(variant, get_variant_id):
    return get_sv_name(variant) or get_variant_id(variant)


def _get_loaded_before_date_project_individual_samples(projects, max_loaded_date):
    max_loaded_date = datetime.strptime(max_loaded_date, '%Y-%m-%d')
    loaded_samples = _get_sorted_search_samples(projects).filter(
        loaded_date__lte=max_loaded_date).select_related('individual')
    #  Only return the oldest sample for each individual
    return {sample.individual: sample for sample in loaded_samples}


def _get_all_project_individual_samples(projects):
    samples_by_individual_id = {s.individual_id: s for s in _get_sorted_search_samples(projects)}
    individuals = Individual.objects.filter(family__project__in=projects)
    return {i: samples_by_individual_id.get(i.id) for i in individuals}


def _get_sorted_search_samples(projects):
    return get_search_samples(projects, active_only=False).order_by('-loaded_date')


HET = 'Heterozygous'
HOM_ALT = 'Homozygous'
HEMI = 'Hemizygous'


# TODO make private
def get_genotype_zygosity(genotype, is_hemi_variant=False):
    num_alt = genotype.get('numAlt')
    cn = genotype.get('cn')
    if num_alt == 2 or cn == 0 or (cn != None and cn > 3):
        return HOM_ALT
    if num_alt == 1 or cn == 1 or cn == 3:
        return HEMI if is_hemi_variant else HET
    return None


# TODO move/ make private
def get_discovery_notes(parent_mnv, mnvs, get_variant_id):
    variant_type = 'complex structural' if parent_mnv.get('svType') else 'multinucleotide'
    parent_name = _get_nested_variant_name(parent_mnv, get_variant_id)
    parent_details = [parent_mnv[key] for key in ['hgvsc', 'hgvsp'] if parent_mnv.get(key)]
    parent = f'{parent_name} ({", ".join(parent_details)})' if parent_details else parent_name
    mnv_names = [_get_nested_variant_name(v, get_variant_id) for v in mnvs]
    nested_mnvs = sorted([v for v in mnv_names if v != parent_name])
    return f'The following variants are part of the {variant_type} variant {parent}: {", ".join(nested_mnvs)}'


def post_process_variant_metadata(v, gene_variants):
    discovery_notes = None
    if len(gene_variants) > 2:
        parent_mnv = next((v for v in gene_variants if len(v['individual_genotype']) == 1), gene_variants[0])
        discovery_notes = get_discovery_notes(
            parent_mnv, gene_variants, get_variant_id=lambda v: f"{v['chrom']}-{v['pos']}-{v['ref']}-{v['alt']}")
    return {
        'sv_name': get_sv_name(v),
        'notes': discovery_notes,
    }


def parse_variant_genetic_findings(variant_models: Iterable[SavedVariant], *args,
                                   variant_json_fields: list[str] = None, variant_model_annotations: dict = None):
    if variant_model_annotations:
        variant_models = variant_models.annotate(**variant_model_annotations)
    variant_json_fields = ['genotypes'] + (variant_json_fields or [])
    variants = []
    gene_ids = set()
    for variant in variant_models:
        chrom, pos = get_chrom_pos(variant.xpos)

        variant_json = variant.saved_variant_json
        variant_json['selectedMainTranscriptId'] = variant.selected_main_transcript_id
        main_transcript = get_variant_main_transcript(variant_json)
        gene_id = main_transcript.get('geneId')
        gene_ids.add(gene_id)

        variants.append({
            'family_id': variant.family_id,
            'chrom': chrom,
            'pos': pos,
            'ref': variant.ref,
            'alt': variant.alt,
            'variant_reference_assembly': GENOME_VERSION_LOOKUP[variant_json['genomeVersion']],
            'gene_id': gene_id,
            'transcript': main_transcript.get('transcriptId'),
            'hgvsc': (main_transcript.get('hgvsc') or '').split(':')[-1],
            'hgvsp': (main_transcript.get('hgvsp') or '').split(':')[-1],
            'seqr_chosen_consequence': main_transcript.get('majorConsequence'),
            **{k: variant_json.get(k) for k in variant_json_fields},
            **{k: getattr(variant, k) for k in variant_model_annotations or {}},
        })

    genes_by_id = get_genes(gene_ids)
    for row in variants:
        row['gene'] = genes_by_id.get(row['gene_id'], {}).get('geneSymbol')
    return variants


def _get_subject_row(individual, has_dbgap_submission, airtable_metadata, individual_ids_map):
    features_present = [feature['id'] for feature in individual.features or []]
    features_absent = [feature['id'] for feature in individual.absent_features or []]
    onset = individual.onset_age

    paternal_ids = individual_ids_map.get(individual.father_id, ('', ''))
    maternal_ids = individual_ids_map.get(individual.mother_id, ('', ''))
    subject_row = {
        'subject_id': individual.individual_id,
        'individual_guid': individual.guid,
        'sex': Individual.SEX_LOOKUP[individual.sex],
        'ancestry': ANCESTRY_MAP.get(individual.population, ''),
        'ancestry_detail': ANCESTRY_DETAIL_MAP.get(individual.population, ''),
        'affected_status': Individual.AFFECTED_STATUS_LOOKUP[individual.affected],
        'congenital_status': Individual.ONSET_AGE_LOOKUP[onset] if onset else 'Unknown',
        'hpo_present': '|'.join(features_present),
        'hpo_absent': '|'.join(features_absent),
        'disorders': individual.disorders,
        'filter_flags': json.dumps(individual.filter_flags) if individual.filter_flags else '',
        'proband_relationship': Individual.RELATIONSHIP_LOOKUP.get(individual.proband_relationship, ''),
        'paternal_id': paternal_ids[0],
        'paternal_guid': paternal_ids[1],
        'maternal_id': maternal_ids[0],
        'maternal_guid': maternal_ids[1],
    }
    if airtable_metadata is not None:
        sequencing = airtable_metadata.get('SequencingProduct') or set()
        subject_row.update({
            'dbgap_submission': 'Yes' if has_dbgap_submission else 'No',
            'dbgap_study_id': airtable_metadata.get('dbgap_study_id', '') if has_dbgap_submission else '',
            'dbgap_subject_id': airtable_metadata.get('dbgap_subject_id', '') if has_dbgap_submission else '',
            'multiple_datasets': 'Yes' if len(sequencing) > 1 or (
            len(sequencing) == 1 and list(sequencing)[0] in MULTIPLE_DATASET_PRODUCTS) else 'No',
        })
    return subject_row


def _get_sample_row(sample, subject_id, has_dbgap_submission, airtable_metadata, include_metadata, get_additional_sample_fields=None):
    sample_row = {
        'subject_id': subject_id,
        'sample_id': sample.sample_id,
    }
    if has_dbgap_submission:
        sample_row['dbgap_sample_id'] = airtable_metadata.get('dbgap_sample_id', '')
    if include_metadata:
        sample_row.update({
            'data_type': sample.sample_type,
            'date_data_generation': sample.loaded_date.strftime('%Y-%m-%d'),
        })
    if get_additional_sample_fields:
        sample_row.update(get_additional_sample_fields(sample, airtable_metadata))
    return sample_row


def get_genetic_findings_rows(rows: list[dict], individual: Individual, participant_id: str,
                              individual_data_types: Iterable[str] = None, family_individuals: dict[str, str] = None,
                              post_process_variant: Callable[[dict, list[dict]], dict] = None, **kwargs) -> list[dict]:
    parsed_rows = []
    variants_by_gene = defaultdict(list)
    for row in (rows or []):
        genotypes = row['genotypes']
        individual_genotype = genotypes.get(individual.guid) or {}
        zygosity = get_genotype_zygosity(individual_genotype)
        if zygosity:
            heteroplasmy = individual_genotype.get('hl')
            findings_id = f'{participant_id}_{row["chrom"]}_{row["pos"]}'
            parsed_row = {
                'genetic_findings_id': findings_id,
                'participant_id': participant_id,
                'zygosity': zygosity if heteroplasmy is None else {
                    HET: 'Heteroplasmy',
                    HOM_ALT: 'Homoplasmy',
                }[zygosity],
                'allele_balance_or_heteroplasmy_percentage': heteroplasmy,
                'variant_inheritance': _get_variant_inheritance(individual, genotypes),
                **row,
                **kwargs,
            }
            if family_individuals is not None:
                parsed_row['additional_family_members_with_variant'] = '|'.join([
                    family_individuals[guid] for guid, g in genotypes.items()
                    if guid != individual.guid and guid in family_individuals and get_genotype_zygosity(g)
                ])
            if individual_data_types is not None:
                parsed_row['method_of_discovery'] = '|'.join([
                    METHOD_MAP.get(data_type) for data_type in individual_data_types if data_type != Sample.SAMPLE_TYPE_RNA
                ])
            parsed_rows.append(parsed_row)
            variants_by_gene[row['gene']].append({**parsed_row, 'individual_genotype': individual_genotype})

    for row in parsed_rows:
        del row['genotypes']
        if post_process_variant:
            row.update(post_process_variant(row, variants_by_gene[row['gene']]))

    return parsed_rows


def _get_variant_inheritance(individual, genotypes):
    parental_inheritance = tuple(
        None if parent is None else genotypes.get(parent.guid, {}).get('numAlt', -1) > 0
        for parent in [individual.mother, individual.father]
    )
    return {
        (True, True): 'biparental',
        (True, False): 'maternal',
        (True, None): 'maternal',
        (False, True): 'paternal',
        (False, False): 'de novo',
        (False, None): 'nonmaternal',
        (None, True): 'paternal',
        (None, False): 'nonpaternal',
        (None, None): 'unknown',
    }[parental_inheritance]


SINGLE_SAMPLE_FIELDS = ['Collaborator', 'dbgap_study_id', 'dbgap_subject_id', 'dbgap_sample_id']
LIST_SAMPLE_FIELDS = ['SequencingProduct', 'dbgap_submission']


def _get_sample_airtable_metadata(sample_ids, user):
    sample_records, _ = get_airtable_samples(
        sample_ids, user, fields=SINGLE_SAMPLE_FIELDS, list_fields=LIST_SAMPLE_FIELDS,
    )
    return sample_records


def _get_parsed_saved_discovery_variants_by_family(families):
    return get_saved_discovery_variants_by_family(
        {'family__id__in': families},
        format_variants=parse_variant_genetic_findings,
        get_family_id=lambda v: v.pop('family_id'),
        variant_json_fields=['svType', 'svName', 'end'],
        variant_model_annotations={
            'gene_known_for_phenotype': Case(When(
                Q(family__post_discovery_omim_numbers__len=0, family__mondo_id__isnull=True),
                then=Value('Candidate')), default=Value('Known')),
        },
    )
