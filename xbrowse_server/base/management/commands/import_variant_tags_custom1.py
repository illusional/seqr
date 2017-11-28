from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.core.management.base import BaseCommand
from pprint import pprint
import xlrd
import re
from django.contrib.auth.models import User

from seqr.views.apis.phenotips_api import get_patient_data
from xbrowse_server.base.models import Family, Individual, ProjectTag, VariantTag
from xbrowse import genomeloc
from django.db.models import Q

def add_variant_tag(row, user):
    project_id = (row.get('Linking ID') or row.get('Link -> project ID')).split('/')[4]
    family_id = (row.get('Family ID') or row.get('CMG Internal Project ID(s)')).strip()
    new_tag_name = row['New Tag'].strip()
    gene_symbol = (row.get('Gene symbol') or row.get('Gene Name')).strip()

    try:
        hgvsc = (row.get('HGVS') or row.get('g. coordinate'))
        hgvsc = hgvsc.strip().split(",")[0]
        chrom, _ = hgvsc.split(":")
        chrom = chrom.replace("chr", "")
        pos_ref, alt = _.split(">")
        pos = re.search("[0-9]+", pos_ref).group(0).strip()
        ref = re.search("[ACGT]+", pos_ref).group(0).strip()
        xpos = genomeloc.get_xpos(chrom, int(pos))
    except Exception as e:
        print("Couldn't parse HGVS: %s in row %s. %s" % (hgvsc, row, e))
        return

    try:
        project_tag = ProjectTag.objects.get(project__project_id=project_id, tag__icontains=new_tag_name)
    except ObjectDoesNotExist as e:
        print("project tag not found - %s %s: %s" % (project_id, new_tag_name, e))
        return
        
    try:
        families = get_family(family_id, project_id=project_id)
    except Exception as e:
        print("Unable to get family: %s %s" % (family_id, e))
        return
    
    assert len(families) == 1
    family = families[0]

    for vt in VariantTag.objects.filter(family=family, xpos=xpos, ref=ref, alt=alt, user=user):
        if any(k in vt.project_tag.tag.lower() for k in ["tier 1", "tier 2", "known gene for phenotype"]):
            print("Variant %s already has tag %s" % (vt,vt.project_tag.tag  ))
            if vt.project_tag.tag != project_tag.tag:
                vt.delete()

    vt, created = VariantTag.objects.get_or_create(project_tag=project_tag, family=family, xpos=xpos, ref=ref, alt=alt, user=user)
    if created:
        print("Creating tag: %s" % (vt.toJSON(),))


AMBIGUOUS = []
def get_family(family_id, project_id=None):
    unchanged_family_id = family_id
    attempts = ['as_is', 'without_suffix'] if '_' in family_id else ['as_is']
    
    if project_id:
        for attempt in attempts:
            try:
                family = Family.objects.get(family_id=family_id, project__project_id=project_id)
                return [family]
            except MultipleObjectsReturned as e:
                raise ValueError("Family %s - multiple found: %s" % (family_id, e))
            except ObjectDoesNotExist as e:
                family_id = "_".join(family_id.split("_")[1:])
                family_id = family_id.split(".")[0]

        raise ValueError("project: %s  family: %s not found" % (project_id, unchanged_family_id))
    else:
        for attempt in attempts:
            families = Family.objects.filter(
                Q(family_id=family_id)
                & (Q(project__project_name__icontains='cmg') | Q(project__project_id__icontains='cmg')) 
                & ~Q(project__project_id__icontains='temp')).distinct()

            if not families:
                families = Family.objects.filter(Q(family_id=family_id) & ~Q(project__project_id__icontains='temp')).distinct()

            if not families:
                family_id = "_".join(family_id.split("_")[1:])
                family_id = family_id.split(".")[0]
                continue
            elif len(families) > 1:
                print("%s %s families returned. Found in: %s" % (family_id, len(families), ", ".join([f.project.project_id for f in families])))
                family_list = [f for f in sorted(families, key=lambda f: f.project.project_id) if f.project.project_id != "Coppens_v18"]
                if len(family_list) > 1:
                    AMBIGUOUS.append( tuple(f.project.project_id for f in family_list) )
                return family_list
            else:
                family = families[0]

            return [family]

        raise ValueError("family: %s not found" % (unchanged_family_id,))


def add_initial_omim(row):
    family_id = row["CMG Internal Project ID(s)"].strip()
    try:
        families = get_family(family_id)
    except Exception as e:
        print("Unable to get family: %s %s" % (family_id, e))


def add_initial_omim(row):
    family_id = row["CMG Internal Project ID(s)"].strip()
    try:
        families = get_family(family_id)
    except Exception as e:
        print("Unable to get family: %s %s" % (family_id, e))

    omim_number = row['OMIM to upload to seqr']
    for family in families:
        individuals = Individual.objects.filter(affected='A')
        if len(individuals) == 0:
            raise ValueError("No affected individuals found in family: " + str(family))

        for individual in individuals:
            patient_data = get_patient_data(family.project, individual.phenotips_id, is_external_id=True)
            pprint(patient_data)

def add_post_discovery_omim(row):
    family_id = row["Family ID (CollPrefix_ID)"].strip()
    try:
        families = get_family(family_id)
    except Exception as e:
        print("Unable to get family: %s %s" % (family_id, e))

    omim_number = row['OMIM # (post-discovery)']
    for family in families:
        family.post_discovery_omim_number = omim_number
        family.save()


def add_coded_phenotype(row):
    family_id = row["Family ID (CollPrefix_ID)"].strip()
    try:
        families = get_family(family_id)
    except Exception as e:
        print("Unable to get family: %s %s" % (family_id, e))

    for family in families:
        family.coded_phenotype = row['Coded phenotype']
        family.save()



class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('variant_tag_file')

    def handle(self, *args, **options):
        xls_file = options.get("variant_tag_file")

        print("Reading " + xls_file)
        
        user = User.objects.get(email = 'samantha@broadinstitute.org')

        print("==============")
        rows = parse_xls(xls_file, worksheet_index=0)  # Tier 1 tags
        for i, row in enumerate(rows):
            if row["New Tag"] == row["Current Tag"]:
                #print("Skipping row %s: tags are the same" % i)
                continue
            add_variant_tag(row, user)

        print("==============")
        rows = parse_xls(xls_file, worksheet_index=1)  # Tier 2 tags
        for i, row in enumerate(rows):
            if row["New Tag"] == row["Current Tag"]:
                #print("Skipping row %s: tags are the same" % i)
                continue
            add_variant_tag(row, user)
        

        print("==============")
        rows = parse_xls(xls_file, worksheet_index=2)  # OMIM #s - Initial
        for i, row in enumerate(rows):
            add_initial_omim(row)

        print("==============")
        rows = parse_xls(xls_file, worksheet_index=3)  # OMIM#s - Post Discovery
        for i, row in enumerate(rows):
            add_post_discovery_omim(row)

        print("==============")
        rows = parse_xls(xls_file, worksheet_index=4)  # Coded Phenotype
        for i, row in enumerate(rows):
            add_coded_phenotype(row)

        print("Ambiguous pairs: ")
        for pair in set(AMBIGUOUS):
            print(pair)

def parse_xls(path, worksheet_index=0):

    wb = xlrd.open_workbook(file_contents=open(path).read())

    ws = wb.sheet_by_index(worksheet_index)
    print("Parsing worksheet: %s" % (ws.name, ))

    header = []
    rows = []
    for i in range(ws.nrows):
        row_fields = [ws.cell(rowx=i, colx=j).value for j in range(ws.ncols)]
        if i == 0 and _is_header_row("\t".join(row_fields)):
            header = row_fields
            continue
        elif not header:
            raise ValueError("Header row not found")

        parsed_row = []
        for j in range(ws.ncols):
            cell = ws.cell(rowx=i, colx=j)
            cell_value = cell.value
            if not cell_value:
                # if the 1st and 2nd column in a row is empty, treat this as the end of the table
                if j == 0 and (ws.ncols < 2 or not ws.cell(rowx=i, colx=1).value):
                    break
                else:
                    parsed_row.append('')
            else:
                if cell.ctype in (2,3) and int(cell_value) == cell_value:
                    cell_value = int(cell_value)
                parsed_row.append(unicode(cell_value).encode('UTF-8'))
        else:
            # keep this row as part of the table
            if len(parsed_row) != len(header):
                raise ValueError("Row %s contains %d columns, while header contains %s: %s" % (
                    i, len(parsed_row), len(header), parsed_row))

            row_dict = dict(zip(header, parsed_row))
            rows.append(row_dict)

    return rows


def _is_header_row(header_row):
    #print("Header row: " + header_row)
    return True
