import json
from django.test import TestCase, override_settings
from testing import fixtures
from identity.models import RoleAssignment
from internal_api.security import signed_headers

KEY='synthetic-pipeline-key-'+'x'*48
PATH='/internal/v1/clients/opportunity-scope'


@override_settings(ROOT_URLCONF='iam_consumer.urls',AICED_INTERNAL_KEYS={'pipeline-test':{'secret':KEY,'service':'commercial','audiences':['client']}})
class PipelineScopeTests(TestCase):
    setUp=fixtures.SecurityFixtures.setUp
    login_as=fixtures.SecurityFixtures.login_as

    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        cls.assignment=RoleAssignment.objects.create(membership=cls.reader_m,role=fixtures.role('pipeline-reader',['opportunities.view']),scope='assigned')

    def send(self,ids=None,headers=None,path=PATH,search=None):
        payload={'credentials':{'session_key':self.client.cookies['sessionid'].value,'method':'GET','host':'testserver','scheme':'http'},
                 'party_ids':[str(p.pk) for p in (ids or [self.own,self.same_org_hidden,self.other_org_hidden])]}
        if search is not None:payload['search']=search
        body=json.dumps(payload).encode()
        headers=headers or signed_headers('pipeline-test',KEY,'client',path,body)
        return self.client.post(path,body,content_type='application/json',**{'HTTP_'+k.upper().replace('-','_'):v for k,v in headers.items() if k!='Content-Type'})

    def test_same_object_intersection_before_metadata_and_can_edit(self):
        self.login_as(self.reader)
        response=self.send()
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['parties'],[{'id':str(self.own.pk),'display_name':self.own.display_name,'can_edit':False}])
        self.assignment.scope='organization';self.assignment.save()
        self.assertEqual(len(self.send().json()['parties']),1)

    def test_revocation_missing_capability_and_prospect_scope(self):
        from clients.models import Prospect
        self.login_as(self.reader)
        Prospect.objects.create(party=self.own)
        self.assertEqual(self.send().json()['parties'],[])
        self.assignment.is_active=False;self.assignment.save()
        self.assertEqual(self.send().status_code,403)

    def test_signature_replay_and_it_denial(self):
        self.login_as(self.it)
        self.assertEqual(self.send().status_code,403)
        self.login_as(self.reader)
        payload={'credentials':{'session_key':self.client.cookies['sessionid'].value,'method':'GET','host':'testserver','scheme':'http'},'party_ids':[str(self.own.pk)]}
        body=json.dumps(payload).encode();headers=signed_headers('pipeline-test',KEY,'client',PATH,body)
        self.assertEqual(self.send([self.own],headers).status_code,200)
        self.assertEqual(self.send([self.own],headers).status_code,403)
        headers['X-Aiced-Signature']='0'*64
        self.assertEqual(self.send([self.own],headers).status_code,403)

    def test_coherence_marker_changes_with_scope_and_cannot_authorize_revocation(self):
        self.login_as(self.reader)
        first=self.send().json()['scope_revision']
        self.assertRegex(first,r'^[a-f0-9]{64}$')
        self.assertEqual(first,self.send().json()['scope_revision'])
        self.assignment.scope='organization';self.assignment.save()
        self.assertNotEqual(first,self.send().json()['scope_revision'])
        self.assignment.is_active=False;self.assignment.save()
        self.assertEqual(self.send().status_code,403)

    def test_compact_scope_payload_bound_search_and_existing_visibility(self):
        from clients.models import Party,PhysicalPerson
        self.login_as(self.reader)
        self.own.display_name='Straße';self.own.save()
        path=PATH+'-batch'
        data=self.send(path=path,search='STRASSE').json()
        self.assertEqual(data['parties'],[{'id':str(self.own.pk),'name_match':True}])
        parties=Party.objects.bulk_create([Party(organization=self.org_a,assigned_to=self.reader_m,kind='physical',display_name='😀'*200) for _ in range(499)])
        PhysicalPerson.objects.bulk_create([PhysicalPerson(party=p,first_name='SYNTHETIC',last_name='S13') for p in parties])
        response=self.send([self.own,*parties],path=path,search='😀')
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.json()['parties']),500)
        self.assertLess(len(response.content),65536)
        self.assertTrue(all(set(row)=={'id','name_match'} for row in response.json()['parties']))
        self.assertEqual(self.send([self.own,*parties,self.same_org_hidden],path=path,search='').status_code,400)
        payload={'credentials':{'session_key':self.client.cookies['sessionid'].value,'method':'GET','host':'testserver','scheme':'http'},'party_ids':[str(self.own.pk)],'search':''}
        body=json.dumps(payload).encode()
        headers=signed_headers('pipeline-test',KEY,'client',path,body)
        self.assertEqual(self.send([self.own],headers,path,'').status_code,200)
        self.assertEqual(self.send([self.own],headers,path,'').status_code,403)
        headers=signed_headers('pipeline-test',KEY,'client',PATH,body)
        self.assertEqual(self.send([self.own],headers,path,'').status_code,403)
        self.login_as(self.it)
        self.assertEqual(self.send(path=path,search='').status_code,403)
