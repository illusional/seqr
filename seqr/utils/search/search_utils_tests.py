from django.contrib.auth.models import User
from django.test import TestCase
import mock

from seqr.models import Family, Sample
from seqr.utils.search.utils import get_single_variant, get_variants_for_variant_ids, get_variant_query_gene_counts, \
    query_variants, InvalidSearchException
from seqr.views.utils.test_utils import PARSED_VARIANTS


class SearchUtilsTests(object):

    def add_model_helpers(self):
        self.families = Family.objects.filter(guid__in=['F000003_3', 'F000002_2', 'F000005_5'])
        self.user = User.objects.get(username='test_user')

    def test_get_single_variant(self, mock_get_variants_for_ids):
        mock_get_variants_for_ids.return_value = [PARSED_VARIANTS[0]]
        variant = get_single_variant(self.families, '2-103343353-GAGA-G', user=self.user)
        self.assertDictEqual(variant, PARSED_VARIANTS[0])
        mock_get_variants_for_ids.assert_called_with(
            self.families, ['2-103343353-GAGA-G'], self.user, return_all_queried_families=False,
        )

        get_single_variant(self.families, '2-103343353-GAGA-G', user=self.user, return_all_queried_families=True)
        mock_get_variants_for_ids.assert_called_with(
            self.families, ['2-103343353-GAGA-G'], self.user, return_all_queried_families=True,
        )

        mock_get_variants_for_ids.return_value = []
        with self.assertRaises(InvalidSearchException) as cm:
            get_single_variant(self.families, '10-10334333-A-G')
        self.assertEqual(str(cm.exception), 'Variant 10-10334333-A-G not found')

    def test_get_variants_for_variant_ids(self, mock_get_variants_for_ids):
        variant_ids = ['2-103343353-GAGA-G', '1-248367227-TC-T', 'prefix-938_DEL']
        get_variants_for_variant_ids(self.families, variant_ids, user=self.user)
        mock_get_variants_for_ids.assert_called_with(self.families, variant_ids, self.user, dataset_type=None)

        get_variants_for_variant_ids(
            self.families, variant_ids, user=self.user, dataset_type=Sample.DATASET_TYPE_VARIANT_CALLS)
        mock_get_variants_for_ids.assert_called_with(
            self.families, variant_ids, self.user, dataset_type=Sample.DATASET_TYPE_VARIANT_CALLS)


@mock.patch('seqr.utils.search.elasticsearch.es_utils.ELASTICSEARCH_SERVICE_HOSTNAME', 'testhost')
class ElasticsearchSearchUtilsTests(TestCase, SearchUtilsTests):
    fixtures = ['users', '1kg_project']

    def setUp(self):
        self.add_model_helpers()

    @mock.patch('seqr.utils.search.utils.get_es_variants_for_variant_ids')
    def test_get_single_variant(self, mock_get_variants_for_ids):
        super(ElasticsearchSearchUtilsTests, self).test_get_single_variant(mock_get_variants_for_ids)

    @mock.patch('seqr.utils.search.utils.get_es_variants_for_variant_ids')
    def test_get_variants_for_variant_ids(self, mock_get_variants_for_ids):
        super(ElasticsearchSearchUtilsTests, self).test_get_variants_for_variant_ids(mock_get_variants_for_ids)


class NoBackendSearchUtilsTests(TestCase, SearchUtilsTests):
    fixtures = ['users', '1kg_project']

    def setUp(self):
        self.add_model_helpers()

    def test_get_single_variant(self):
        with self.assertRaises(InvalidSearchException) as cm:
            super(NoBackendSearchUtilsTests, self).test_get_single_variant(mock.MagicMock())
        self.assertEqual(str(cm.exception), 'Elasticsearch backend is disabled')

    def test_get_variants_for_variant_ids(self):
        with self.assertRaises(InvalidSearchException) as cm:
            super(NoBackendSearchUtilsTests, self).test_get_variants_for_variant_ids(mock.MagicMock())
        self.assertEqual(str(cm.exception), 'Elasticsearch backend is disabled')