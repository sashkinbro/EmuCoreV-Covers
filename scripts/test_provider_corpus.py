import unittest
from provider_corpus import extend_catalog,release_review

class ProviderCorpusTests(unittest.TestCase):
    def test_provider_art_is_keyed_by_id_without_serial_or_release_inference(self):
        catalog={'games':[{'igdb_id':1,'name':'Same Name','cover_url':'old'}]}
        metadata={'games':[{'id':1,'name':'Same Name','platforms':[46],'cover':{'url':'old'}},{'id':2,'name':'Same Name','platforms':[46],'game_type':1,'cover':{'url':'new'}},{'id':3,'name':'No Art','platforms':[46]}]}
        review={'all104_new':[{'id':2,'review_class':'non_base_content_provider_type','review_reason':'DLC'},{'id':3,'review_class':'provider_cover_unavailable'}],'historical33':[]}
        out,added=extend_catalog(catalog,metadata,review,'hash')
        self.assertEqual(added,['2']);self.assertEqual(len(out['games']),2)
        self.assertEqual(out['games'][1]['provider_game_type'],1)
        self.assertFalse(out['games'][1]['native_release_asserted'])
        self.assertNotIn('serials',out);self.assertNotIn('native_identity_title_ids',out['games'][1])
        again,added=extend_catalog(out,metadata,review,'hash')
        self.assertEqual(again,out);self.assertEqual(added,[])

    def test_global_status_and_dated_provider_rows_do_not_override_platform_conflict(self):
        facts={'games':[{'id':136713,'name':'Konosuba Plus','game_status':{'status':'released'},'release_dates':[{'date':1,'platform':48}]},{'id':2,'name':'Conflict','release_dates':[{'date':1,'platform':46}]}]}
        review={'all104_new':[{'id':136713,'review_class':'provider_platform_conflict'},{'id':2,'review_class':'provider_platform_conflict'}],'historical33':[]}
        rows=release_review(facts,review)['records']
        self.assertEqual(rows[0]['provider_release_evidence_shape'],'no_vita_release_row')
        self.assertEqual(rows[1]['provider_release_evidence_shape'],'dated_vita_row')
        self.assertTrue(all(r['publisher_or_developer_platform_conflict'] for r in rows))
        self.assertTrue(all(r['automatic_native_promotion_or_serial_join'] is False for r in rows))

if __name__=='__main__':unittest.main()
