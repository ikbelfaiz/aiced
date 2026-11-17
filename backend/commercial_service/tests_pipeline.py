from uuid import UUID,uuid4
from unittest.mock import patch
from django.test import SimpleTestCase
from commercial_service.access import Actor
from commercial_service.pipeline import scope_parties
from internal_api.client import ServiceUnavailable
from commercial_service.pipeline import scan,remaining,database_fail_closed
from types import SimpleNamespace
from time import monotonic
from django.db import OperationalError


class PipelineTrustTests(SimpleTestCase):
    def test_invalid_peer_identity_unknown_ids_duplicates_and_flags_fail_closed(self):
        actor=Actor(uuid4(),'synthetic',{})
        ident=str(uuid4())
        valid={'id':ident,'display_name':'SYNTHETIC','can_edit':False}
        for response in [
            {'actor_id':str(uuid4()),'parties':[valid]},
            {'actor_id':str(actor.pk),'parties':[{**valid,'id':str(uuid4())}]},
            {'actor_id':str(actor.pk),'parties':[valid,valid]},
            {'actor_id':str(actor.pk),'parties':[{**valid,'can_edit':'true'}]},
            {'actor_id':str(actor.pk),'parties':[{**valid,'display_name':''}]},
        ]:
            with patch('commercial_service.pipeline.peer') as peer:
                peer.return_value.post.return_value=response
                with self.assertRaises(ServiceUnavailable):scope_parties(actor,[ident])

    def test_signed_calls_bounded_and_empty_scope_still_checked(self):
        actor=Actor(uuid4(),'synthetic',{'session_key':'synthetic'})
        ids=[str(uuid4()) for _ in range(101)]
        with patch('commercial_service.pipeline.peer') as peer:
            peer.return_value.post.return_value={'actor_id':str(actor.pk),'parties':[]}
            self.assertEqual(scope_parties(actor,ids),{})
            calls=peer.return_value.post.call_args_list
            self.assertEqual([len(c.args[1]['party_ids']) for c in calls],[100,1])
            scope_parties(actor,[])
            self.assertEqual(peer.return_value.post.call_args.args[1]['party_ids'],[])


class PipelineStreamTests(SimpleTestCase):
    def stream(self,n):
        class Stream:
            def iterator(self,chunk_size):
                assert chunk_size==500
                for i in range(n):
                    yield SimpleNamespace(id=i,party_id=UUID(int=i+1),status=['open','won','lost'][i%3],pipeline_text_match=i%2==0)
        return Stream()

    def scope(self,actor,ids,deadline,scope_state=None,**kwargs):
        self.assertLessEqual(len(ids),500)
        return {i:{'name_match':True} for i in ids if UUID(i).int%2==0}

    def test_ten_thousand_visibility_before_counts_and_deep_pagination(self):
        with patch('commercial_service.pipeline.scope_parties',side_effect=self.scope) as scope:
            count,counts,rows=scan(None,self.stream(10000),{'page':100,'page_size':50},monotonic()+12)
        self.assertEqual(count,5000)
        self.assertEqual(sum(counts.values()),5000)
        self.assertEqual([r.id for r in rows],list(range(9901,10000,2)))
        self.assertEqual(scope.call_count,20)

    def test_search_status_counts_and_no_partial_result_on_timeout(self):
        with patch('commercial_service.pipeline.scope_parties',side_effect=self.scope):
            count,counts,rows=scan(None,self.stream(1001),{'search':'match','status':'won','page_size':50},monotonic()+12)
            self.assertEqual(count,counts['won'])
            self.assertEqual(sum(counts.values()),500)
            self.assertTrue(all(r.status=='won' for r in rows))
        with self.assertRaises(ServiceUnavailable):remaining(monotonic()-1)
        with patch('commercial_service.pipeline.scope_parties',side_effect=ServiceUnavailable()):
            with self.assertRaises(ServiceUnavailable):scan(None,self.stream(1000),{},monotonic()+12)

    def test_database_failure_maps_to_safe_unavailable(self):
        @database_fail_closed
        def failing():raise OperationalError('synthetic unavailable database')
        with self.assertRaises(ServiceUnavailable):failing()

    def test_scope_revision_changed_expired_or_missing_fails_closed(self):
        actor=Actor(uuid4(),'synthetic',{})
        state=[]
        with patch('commercial_service.pipeline.peer') as peer:
            peer.return_value.post.return_value={'actor_id':str(actor.pk),'parties':[],'scope_revision':'a'*64}
            scope_parties(actor,[],scope_state=state)
            self.assertEqual(state,['a'*64])
            for revision in ['b'*64,None,'invalid']:
                peer.return_value.post.return_value={'actor_id':str(actor.pk),'parties':[],'scope_revision':revision}
                with self.assertRaises(ServiceUnavailable):scope_parties(actor,[],scope_state=state)

    def test_compact_scope_bound_invalid_flags_and_unknown_objects(self):
        actor=Actor(uuid4(),'synthetic',{})
        ids=[str(uuid4()) for _ in range(501)]
        with patch('commercial_service.pipeline.peer') as peer:
            peer.return_value.post.return_value={'actor_id':str(actor.pk),'parties':[]}
            scope_parties(actor,ids,compact=True,search='SYNTHETIC')
            self.assertEqual([len(c.args[1]['party_ids']) for c in peer.return_value.post.call_args_list],[500,1])
            self.assertTrue(all(c.args[0].endswith('-batch') for c in peer.return_value.post.call_args_list))
            for row in [{'id':ids[0],'name_match':'true'},{'id':str(uuid4()),'name_match':True}]:
                peer.return_value.post.return_value={'actor_id':str(actor.pk),'parties':[row]}
                with self.assertRaises(ServiceUnavailable):scope_parties(actor,ids[:1],compact=True)
