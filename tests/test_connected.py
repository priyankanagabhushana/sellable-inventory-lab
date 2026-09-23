"""Regression tests for executable contracts and connected forecast decisions."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from allotment import allot, build_breaks, allocation_trace
from contracts import programme_errors, allocation_errors
from forecast_workbench import (generate_history, add_history_features, evaluate_models,
    bands_for_predictions, forecast_breaks, predict_raw, tree_explanation)
from learning_data import stable_case, data_quality_report
from schedule_source import stable_demo_schedule, load_schedule


class ConnectedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = generate_history(with_features=False)
        cls.history = add_history_features(cls.raw)
        cls.artifacts = evaluate_models(cls.history)
        cls.case = stable_case(cls.artifacts)

    def test_schedule_does_not_overlap_and_breaks_fit_programmes(self):
        self.assertEqual(programme_errors(self.case['programmes']), [])
        report = data_quality_report(self.case['programmes'], self.case['breaks'], self.case['requests'], self.case['placements'])
        self.assertTrue(report.status.eq('PASS').all())
        b = self.case['breaks']
        self.assertTrue((b.air_time < b.forecast_issue_time + pd.DateOffset(weeks=1)).all())

    def test_reject_duplicate_and_overlapping_programmes(self):
        p = self.case['programmes']
        with self.assertRaises(ValueError):
            build_breaks(pd.concat([p, p.iloc[[0]]]))
        p = p.copy()
        p.loc[1,'start'] = p.loc[0,'start']
        p.loc[1,'duration_min'] = (p.loc[1,'stop']-p.loc[1,'start']).total_seconds()/60
        with self.assertRaises(ValueError):
            build_breaks(p)

    def test_invalid_inputs_stop_allocation(self):
        for column,value in [('request_id',None),('spot_sec',-30),('goal_impressions',np.inf),('max_spots',1.5)]:
            with self.subTest(column=column):
                r = self.case['requests'].copy()
                if column in ['goal_impressions','max_spots']:
                    r[column] = r[column].astype(float)
                r.loc[0,column] = value
                with self.assertRaises(ValueError):
                    allot(self.case['breaks'],r)
        with self.assertRaises(ValueError):
            allot(self.case['breaks'],pd.concat([self.case['requests'],self.case['requests'].iloc[[0]]]))

    def test_corrupt_placement_is_not_reported_as_clean(self):
        for column,value in [('break_id','nonexistent'),('request_id','nonexistent'),('spot_sec',9999)]:
            with self.subTest(column=column):
                p=self.case['placements'].copy(); p.loc[0,column]=value
                report=data_quality_report(self.case['programmes'],self.case['breaks'],self.case['requests'],p)
                self.assertTrue(report.status.eq('FAIL').any())

    def test_presold_plus_new_seconds_is_checked(self):
        b=self.case['breaks'].copy()
        bid=self.case['placements'].iloc[0].break_id
        b.loc[b.break_id==bid,'presold_sec']=b.loc[b.break_id==bid,'capacity_sec']
        self.assertIn('Placements: total used seconds exceed capacity',allocation_errors(b,self.case['requests'],self.case['placements']))

    def test_quantiles_ordered_for_biased_and_negative_predictions(self):
        for q in [(10,15,20),(-20,-15,-10),(-20,0,20)]:
            bands=bands_for_predictions([-100,0,100],q)
            self.assertTrue((np.diff(bands,axis=1)>=0).all())
            self.assertTrue((bands>=0).all())
        self.assertEqual(bands_for_predictions([100],(10,15,20))[0,1],115)

    def test_future_outcomes_do_not_change_earlier_features_or_training(self):
        changed=self.raw.copy()
        boundary=self.artifacts.predictions.forecast_issue_time.min() + pd.DateOffset(weeks=2)
        changed.loc[changed.date>=boundary,'actual_audience']*=5
        recomputed=add_history_features(changed)
        before=self.history[self.history.date<boundary].reset_index(drop=True)
        pd.testing.assert_frame_equal(before,recomputed[recomputed.date<boundary].reset_index(drop=True))
        altered=evaluate_models(recomputed)
        self.assertEqual(self.artifacts.model.get_booster().get_dump(),altered.model.get_booster().get_dump())
        self.assertEqual(self.artifacts.calibration_quantiles,altered.calibration_quantiles)
        old=self.artifacts.predictions.query('date < @boundary').reset_index(drop=True)
        new=altered.predictions.query('date < @boundary').reset_index(drop=True)
        pd.testing.assert_frame_equal(old,new)

    def test_forecasts_use_only_available_observations(self):
        for rows in [self.history,self.case['features']]:
            self.assertTrue((rows.feature_available_at < rows.forecast_issue_time).all())
            self.assertTrue((rows.date < rows.forecast_issue_time + pd.DateOffset(weeks=1)).all())
        self.assertLess(self.artifacts.training_cutoff,self.artifacts.calibration_start)

    def test_allocation_uses_forecasts_from_selected_model(self):
        for method in self.artifacts.calibration_quantiles:
            b,features=forecast_breaks(build_breaks(self.case['programmes']),self.artifacts,method)
            raw=predict_raw(features,method,self.artifacts.models,self.artifacts.feature_columns)
            expected=bands_for_predictions(raw,self.artifacts.calibration_quantiles[method])
            np.testing.assert_allclose(b[['adults_p20','adults_p50','adults_p80']],expected)
            p,s,fill=allot(b,self.case['requests'])
            self.assertTrue(p.model_name.eq(method).all())
            self.assertTrue(p.training_cutoff.eq(self.artifacts.training_cutoff).all())
            self.assertEqual(allocation_errors(b,self.case['requests'],p),[])
            self.assertTrue((fill.used_sec<=fill.capacity_sec).all())
            expected_sums=p.groupby('request_id')[['target_p20','target_p50']].sum()
            for row in s.itertuples():
                if row.request_id in expected_sums.index:
                    self.assertEqual(row.planned_p20,expected_sums.loc[row.request_id,'target_p20'])

    def test_tree_paths_and_contributions_match_model(self):
        for i in [0,50,200]:
            explanation=tree_explanation(self.artifacts,self.case['features'].iloc[i],2)
            self.assertAlmostEqual(explanation['reconstructed'],explanation['raw_prediction'],delta=.1)
            self.assertEqual(explanation['path'][-1]['node_id'],explanation['leaf_ids'][2])

    def test_trace_matches_actual_selection(self):
        for policy in ['firm_first','first_come']:
            p,_,_=allot(self.case['breaks'],self.case['requests'],policy)
            for rid in self.case['requests'].request_id:
                trace=allocation_trace(self.case['breaks'],self.case['requests'],rid,policy)
                chosen=set(trace.loc[trace.reason.str.startswith('Selected'),'break_id'])
                self.assertEqual(chosen,set(p.loc[p.request_id==rid,'break_id']))

    def test_empty_eligible_pool_has_zero_delivery_and_valid_schema(self):
        r=self.case['requests'].iloc[[0]].copy()
        r['eligible_channels']='unavailable'
        p,s,fill=allot(self.case['breaks'],r)
        self.assertTrue(p.empty)
        self.assertIn('break_id',p)
        self.assertEqual(s.iloc[0].spots,0)
        self.assertEqual(s.iloc[0].planned_p20,0)

    def test_connected_case_works_without_network(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('unexpected network access')):
            case=stable_case(self.artifacts)
        self.assertGreater(len(case['placements']),0)

    def test_invalid_public_schedule_falls_back(self):
        invalid=pd.concat([self.case['programmes'],self.case['programmes'].iloc[[0]]])
        with patch('schedule_source.fetch_schedule',return_value=invalid):
            schedule,source=load_schedule(refresh=True,allow_remote=True)
        self.assertIn('refresh failed',source)
        self.assertEqual(programme_errors(schedule),[])

    def test_options_do_not_change_firm_results_with_model_forecasts(self):
        _,all_rows,_=allot(self.case['breaks'],self.case['requests'])
        _,firm,_=allot(self.case['breaks'],self.case['requests'].query("status == 'firm'"))
        pd.testing.assert_frame_equal(all_rows.query("status == 'firm'").reset_index(drop=True),firm.reset_index(drop=True))


if __name__=='__main__':
    unittest.main()
