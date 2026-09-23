"""Exercise the real router so navigation and shared selections are tested."""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class LearningFlowTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT / 'app.py'), default_timeout=60).run()

    def test_campaign_model_break_and_policy_survive_navigation_and_reset(self):
        app = self.app()
        app.selectbox(key='_lab_home_campaign').set_value('C04').run()
        app.selectbox(key='_lab_home_model').set_value('seasonal_naive').run()
        selected_break = app.session_state['lab_break']
        for path in ['pages/1_Data_and_SQL.py','pages/2_Forecasting_Workbench.py','pages/3_Allocation_Lab.py']:
            app.switch_page(path).run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.session_state['lab_campaign'],'C04')
            self.assertEqual(app.session_state['lab_model'],'seasonal_naive')
            self.assertEqual(app.session_state['lab_break'],selected_break)
        app.selectbox(key='_lab_allocation_policy').set_value('first_come').run()
        app.selectbox(key='_lab_allocation_planning').set_value('p50').run()
        app.switch_page('home_page.py').run()
        self.assertEqual(app.session_state['lab_policy'],'first_come')
        self.assertEqual(app.session_state['lab_planning'],'p50')
        app.button[0].click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state['lab_campaign'],'C01')
        self.assertEqual(app.session_state['lab_model'],'xgboost')

    def test_bad_data_example_is_caught_and_can_be_reset(self):
        app=self.app().switch_page('pages/1_Data_and_SQL.py').run()
        select=next(s for s in app.selectbox if s.label=='Temporary example')
        select.select('Missing campaign ID').run()
        self.assertEqual(len(app.exception),0)
        self.assertGreater(len(app.error),0)
        app.button[0].click().run()
        self.assertEqual(app.selectbox(key='_lab_mistake').value,'Clean data')
        select=next(s for s in app.selectbox if s.label=='Temporary example')
        select.select('Clean data').run()
        self.assertEqual(len(app.error),0)

    def test_prediction_question_reveals_reasoning(self):
        app=self.app()
        self.assertEqual(len(app.success),0)
        app.radio[0].set_value('No, because 40 seconds will not fit').run()
        self.assertGreater(len(app.success),0)


if __name__=='__main__':
    unittest.main()
