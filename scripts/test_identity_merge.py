import unittest
from pipeline import normalize,resolve
from worldwide_sources import type_name
from worldwide_merge import merge_additions,apply_dispositions,eligible_names,source_anomalies

class IdentityRegressionTests(unittest.TestCase):
    def test_plus_signs_separate_actual_sayonara_editions(self):
        self.assertNotEqual(normalize('Sayonara UmiharaKawase +'),normalize('Sayonara UmiharaKawase ++'))
        games={'27109':{'name':'Sayonara Umihara Kawase +'},'110017':{'name':'Sayonara UmiharaKawase ++'}}
        self.assertNotIn('110017',resolve('Sayonara UmiharaKawase +',games))
        self.assertNotIn('27109',resolve('Sayonara Umihara Kawase ++',games))

    def test_trial_in_a_game_title_is_not_a_demo_label(self):
        self.assertEqual(type_name('Urban Trial Freestyle','base_application'),'base_application')
        self.assertEqual(type_name('Urban Trial Freestyle','reported_application'),'reported_application')
        self.assertEqual(type_name('Urban Trial Freestyle Demo','base_application'),'demo')
        self.assertEqual(type_name('Gravity Rush Trial Version','base_application'),'demo')
        self.assertEqual(type_name('ゲーム体験版','base_application'),'demo')
        self.assertEqual(type_name('Tearaway (Trial & Unlock)','base_application'),'trial_and_unlock')

    def test_additive_source_cannot_overwrite_an_existing_mapping(self):
        with self.assertRaises(ValueError):merge_additions({'PCSB01199':{'igdb_id':'27109'}},{'serials':{'PCSB01199':'110017'},'serial_metadata':{}},{'110017':{}})

    def test_explicit_edition_review_corrects_known_wrong_map_and_blocks_version_ambiguity(self):
        initial={'PCSB01199':{'igdb_id':'27109'},'PCSE00640':{'igdb_id':'7444'},'PCSB00031':{'igdb_id':'5258'}}
        evidence=['https://www.strictlylimitedgames.com/blogs/strictly-limited-games-releases/sayonara-umiharakawase']
        ds={'existing':{'PCSB01199':{'selected_igdb_id':'110017','evidence':evidence,'rationale':'Explicit ++ product'},'PCSE00640':{'selected_igdb_id':None},'PCSB00031':{'selected_igdb_id':'42707','evidence':evidence,'rationale':'Explicit Vita World Tour Edition'}},'additional_conflict_resolutions':{}}
        out=apply_dispositions(initial,ds,{'110017':{'name':'Sayonara UmiharaKawase ++'},'42707':{'name':'Virtua Tennis 4: World Tour Edition'}})
        self.assertEqual(out['PCSB01199']['igdb_id'],'110017');self.assertEqual(out['PCSB00031']['igdb_id'],'42707');self.assertNotIn('PCSE00640',out)
        self.assertEqual(out['PCSB01199']['title'],'Sayonara UmiharaKawase ++')
        self.assertEqual(out['PCSB01199']['evidence'][0]['title'],'Sayonara UmiharaKawase ++')

    def test_conflicting_dlc_identifiers_are_logged_without_rewriting_or_mapping(self):
        row={'title_id':'PCSE00001','content_id':'UP0000-PCSE00002_00-ABCDEFGHIJKLMNOP','content_type':'dlc','source':'fixture','source_record_id':'3','evidence_url':'https://example.org/source'}
        before=dict(row);out=source_anomalies([row])
        self.assertEqual(row,before);self.assertEqual(len(out),1)
        self.assertEqual(out[0]['declared_title_id'],'PCSE00001');self.assertEqual(out[0]['content_id_title_id'],'PCSE00002')
        self.assertFalse(out[0]['automatic_parent_or_runtime_join_allowed'])
        self.assertEqual(source_anomalies([dict(row,content_id='UP0000-PCSE00001_00-ABCDEFGHIJKLMNOP')]),[])

    def test_collectors_package_alias_does_not_capture_the_base_edition(self):
        g={'id':72067,'name':"Catherine: Full Body - Heart's Desire Premium Edition",'alternative_names':[{'id':1,'name':'キャサリン・フルボディ','comment':'Japanese title'}]}
        self.assertEqual(len(list(eligible_names(g))),1)

if __name__=='__main__':unittest.main()
