from django.test import TestCase
from testing import fixtures
from clients.models import CRMProfile, Prospect


class SegmentationTests(TestCase):
    setUp=fixtures.SecurityFixtures.setUp
    login_as=fixtures.SecurityFixtures.login_as

    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        CRMProfile.objects.filter(party=cls.own).update(profession='SYNTHETIC Engineer',sector='Industry')
        CRMProfile.objects.filter(party=cls.same_org_hidden).update(profession='SECRET A',sector='SECRET A')
        CRMProfile.objects.filter(party=cls.other_org_hidden).update(profession='SECRET B',sector='SECRET B')

    def test_options_and_counts_scope_before_aggregation(self):
        self.login_as(self.reader)
        data=self.client.get('/api/clients/filter-options/').json()
        self.assertEqual(data['profession']['values'],[{'value':'SYNTHETIC Engineer','count':1}])
        self.assertNotIn('SECRET',str(data))
        self.assertEqual(self.client.get('/api/clients/?profession=SECRET%20A').json()['count'],0)

    def test_combined_filters_search_and_sort_pages(self):
        self.login_as(self.reader)
        for name in ['SYNTHETIC B','SYNTHETIC A']:
            p=fixtures.party(self.org_a,self.reader_m,name)
            CRMProfile.objects.filter(party=p).update(profession='SYNTHETIC Engineer',sector='Industry')
        url='/api/clients/?profession=SYNTHETIC%20Engineer&sector=Industry&kind=physical&search=SYNTHETIC&ordering=display_name&page_size=1'
        first=self.client.get(url).json(); second=self.client.get(url+'&page=2').json()
        self.assertEqual(first['count'],3)
        self.assertEqual(first['results'][0]['display_name'],'SYNTHETIC A')
        self.assertNotEqual(first['results'][0]['id'],second['results'][0]['id'])
        self.assertEqual(self.client.get(url.replace('Industry','Other')).json()['count'],0)

    def test_missing_absent_profile_whitespace_and_variants(self):
        self.login_as(self.reader)
        CRMProfile.objects.filter(party=self.own).delete()
        self.assertEqual(self.client.get('/api/clients/?profession_missing=true').json()['count'],1)
        CRMProfile.objects.create(party=self.own,profession=' \t ',sector='')
        self.assertEqual(self.client.get('/api/clients/filter-options/').json()['profession']['missing_count'],1)
        self.assertEqual(self.client.get('/api/clients/?sector_missing=true').json()['count'],1)
        for value in ['Engineer','engineer',' Engineer ']:
            p=fixtures.party(self.org_a,self.reader_m,'SYNTHETIC '+value)
            CRMProfile.objects.filter(party=p).update(profession=value)
        data=self.client.get('/api/clients/filter-options/').json()
        self.assertEqual(len(data['profession']['values']),3)
        self.assertEqual(self.client.get('/api/clients/?profession=%20Engineer%20').json()['count'],1)
        self.assertEqual(self.client.get('/api/clients/?profession_missing=false').json()['count'],3)

    def test_prospects_excluded_and_revocation_denies_both_routes(self):
        self.login_as(self.reader)
        Prospect.objects.create(party=self.own)
        self.assertEqual(self.client.get('/api/clients/filter-options/').json()['profession']['values'],[])
        self.reader_grant.is_active=False; self.reader_grant.save()
        for url in ['/api/clients/','/api/clients/filter-options/']:
            self.assertEqual(self.client.get(url).status_code,403)

    def test_invalid_filters_and_it_anonymous(self):
        self.assertEqual(self.client.get('/api/clients/filter-options/').status_code,403)
        self.login_as(self.it)
        self.assertEqual(self.client.get('/api/clients/filter-options/').status_code,403)
        self.login_as(self.reader)
        for query in ['profession_missing=bad','ordering=bad','profession='+('x'*121),'profession_missing=true&profession=Engineer']:
            self.assertEqual(self.client.get('/api/clients/?'+query).status_code,400)

    def test_crm_sort_nulls_last_and_uuid_ties(self):
        self.login_as(self.reader)
        missing=fixtures.party(self.org_a,self.reader_m,'SYNTHETIC missing')
        tie=fixtures.party(self.org_a,self.reader_m,'SYNTHETIC tie')
        CRMProfile.objects.filter(party=tie).update(profession='SYNTHETIC Engineer',sector='Industry')
        for field in ['profession','sector']:
            for direction in ['', '-']:
                data=self.client.get('/api/clients/?ordering='+direction+field).json()
                ids=[row['id'] for row in data['results']]
                self.assertEqual(ids[-1],str(missing.pk))
                self.assertEqual(ids[:2],sorted([str(self.own.pk),str(tie.pk)]))
