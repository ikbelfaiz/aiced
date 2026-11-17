from unittest.mock import patch
from django.test import TestCase
from testing import fixtures
from clients.models import CRMProfile


class QualityTests(TestCase):
    setUp=fixtures.SecurityFixtures.setUp
    login_as=fixtures.SecurityFixtures.login_as

    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        CRMProfile.objects.filter(party=cls.own).update(email='synthetic@example.invalid',phone=' \t ',profession='Engineer',sector='')
        CRMProfile.objects.filter(party=cls.same_org_hidden).update(email='hidden@example.invalid',phone='1',profession='SECRET',sector='SECRET')

    def test_scoped_summary_and_detail(self):
        self.login_as(self.reader)
        data=self.client.get('/api/clients/filter-options/').json()['quality']
        self.assertEqual((data['total'],data['complete'],data['incomplete']),(1,0,1))
        self.assertEqual(data['missing_counts'],{'email':0,'phone':1,'profession':0,'sector':1})
        own=self.client.get(f'/api/clients/{self.own.pk}/quality/').json()
        self.assertEqual(own['percentage'],50)
        self.assertEqual([f['key'] for f in own['missing_fields']],['phone','sector'])
        for party in [self.same_org_hidden,self.other_org_hidden]:
            self.assertEqual(self.client.get(f'/api/clients/{party.pk}/quality/').status_code,404)
        self.assertNotIn('SECRET',str(data))

    def test_combination_ranges_search_order_pages(self):
        self.login_as(self.reader)
        for label in ['SYNTHETIC B','SYNTHETIC A']:
            p=fixtures.party(self.org_a,self.reader_m,label)
            CRMProfile.objects.filter(party=p).update(profession='Engineer',email='synthetic@example.invalid')
        url='/api/clients/?profession=Engineer&kind=physical&completeness_min=50&completeness_max=50&missing_field=phone&search=SYNTHETIC&ordering=display_name&page_size=1'
        a=self.client.get(url).json();b=self.client.get(url+'&page=2').json()
        self.assertEqual(a['count'],3)
        self.assertEqual(a['results'][0]['display_name'],'SYNTHETIC A')
        self.assertNotEqual(a['results'][0]['id'],b['results'][0]['id'])
        self.assertEqual(self.client.get('/api/clients/?completeness_min=51').json()['count'],0)

    def test_absent_profile_and_disabled_definition(self):
        self.login_as(self.reader)
        CRMProfile.objects.filter(party=self.own).delete()
        self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/quality/').json()['percentage'],0)
        with patch.dict('os.environ',{'AICED_PROFILE_COMPLETENESS_FIELDS':''}):
            data=self.client.get('/api/clients/filter-options/').json()['quality']
            self.assertFalse(data['available']);self.assertIsNone(data['complete'])
            self.assertIsNone(self.client.get(f'/api/clients/{self.own.pk}/quality/').json()['percentage'])
            self.assertEqual(self.client.get('/api/clients/?completeness_min=0').status_code,400)
        with patch.dict('os.environ',{'AICED_PROFILE_COMPLETENESS_FIELDS':'email,phone,sector'}):
            self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/quality/').json()['percentage'],0)

    def test_validation_revocation_it_and_empty(self):
        self.login_as(self.reader)
        for query in ['completeness_min=-1','completeness_max=101','completeness_min=80&completeness_max=20','missing_field=risk']:
            self.assertEqual(self.client.get('/api/clients/?'+query).status_code,400)
        self.reader_grant.is_active=False;self.reader_grant.save()
        self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/quality/').status_code,403)
        self.login_as(self.it)
        self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/quality/').status_code,403)

    def test_configured_equal_weights_floor(self):
        self.login_as(self.reader)
        with patch.dict('os.environ',{'AICED_PROFILE_COMPLETENESS_FIELDS':'email,phone,sector'}):
            self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/quality/').json()['percentage'],33)

    def test_variants_are_only_diagnostic_and_empty_population(self):
        self.login_as(self.reader)
        for value in ['engineer',' Engineer ']:
            p=fixtures.party(self.org_a,self.reader_m,'SYNTHETIC variant')
            CRMProfile.objects.filter(party=p).update(profession=value)
        q=self.client.get('/api/clients/filter-options/').json()
        self.assertEqual(q['quality']['formatting']['profession'],{'variant_groups':1,'edge_whitespace_count':1})
        self.assertEqual(len(q['profession']['values']),3)
        from clients.models import Party
        Party.objects.filter(assigned_to=self.reader_m).update(assigned_to=None)
        q=self.client.get('/api/clients/filter-options/').json()
        self.assertEqual(q['quality']['total'],0)
        self.assertEqual(q['quality']['complete'],0)
        self.assertEqual(q['kind'],[])
