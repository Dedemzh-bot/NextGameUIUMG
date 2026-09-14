"""Explicit no-wrap reset must survive validation and plan lowering."""
import copy, unittest
from pathlib import Path
from test_text_component_rules import split_header_spec, CATALOG_PATH
from validate_layout_spec import load_json, validate_spec
from prepare_build import build_plan

class NoWrapResetTests(unittest.TestCase):
    def setUp(self):
        self.spec=copy.deepcopy(split_header_spec())
        self.node=self.spec['nodes'][2]
        self.catalog=load_json(CATALOG_PATH)
    def codes(self): return {e['code'] for e in validate_spec(self.spec,self.catalog)['errors']}
    def test_explicit_no_wrap_zero_valid(self):
        self.node['properties'].update(autoWrap=False,wrapTextAt=0)
        self.assertTrue(validate_spec(self.spec,self.catalog)['valid'])
    def test_wrapping_zero_invalid(self):
        self.node['properties'].update(autoWrap=True,wrapTextAt=0)
        self.assertIn('text.wrap_width.required',self.codes())
    def test_unspecified_zero_invalid(self):
        self.node['properties'].pop('autoWrap',None);self.node['properties']['wrapTextAt']=0
        self.assertIn('text.wrap_width.positive',self.codes())
    def test_negative_invalid(self):
        self.node['properties'].update(autoWrap=False,wrapTextAt=-1)
        self.assertIn('text.wrap_width.positive',self.codes())
    def test_boolean_width_invalid(self):
        self.node['properties'].update(autoWrap=False,wrapTextAt=False)
        self.assertIn('text.wrap_width.positive',self.codes())
    def test_plan_contains_both_resets(self):
        self.node['properties'].update(autoWrap=False,wrapTextAt=0)
        rules=load_json(CATALOG_PATH.parent/'rule-index.json')
        plan=build_plan(Path('no-wrap-reset.json'),self.spec,self.catalog,rules)
        step=next(s for s in plan['steps'] if s['stepId']=='set-widget-properties-header-title')
        values=step['arguments']['values']
        self.assertEqual(values['wrapTextAt'],0)
        self.assertIs(values['autoWrapText'],False)

if __name__=='__main__': unittest.main()
