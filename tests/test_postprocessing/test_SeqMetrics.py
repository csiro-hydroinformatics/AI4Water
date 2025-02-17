import os
import unittest
import site   # so that ai4water directory is in path
import sys
ai4_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print('ai4w_dir', ai4_dir)
site.addsitedir(ai4_dir)

import numpy as np

from ai4water.postprocessing.SeqMetrics import RegressionMetrics, ClassificationMetrics
from ai4water.postprocessing.SeqMetrics.utils import plot_metrics
from ai4water.postprocessing.SeqMetrics.utils import list_subclass_methods


t = np.random.random((20, 1))
p = np.random.random((20, 1))

er = RegressionMetrics(t, p)

all_errors = er.calculate_all()

not_metrics = ['calculate_all',
               'stats',
               "treat_arrays",
               "scale_free_metrics",
               "scale_dependent_metrics",
               "composite_metrics",
               "relative_metrics",
               "percentage_metrics"]

predictions = np.array([[0.25, 0.25, 0.25, 0.25],
                        [0.01, 0.01, 0.01, 0.96]])
targets = np.array([[0, 0, 0, 1],
                   [0, 0, 0, 1]])

class_metrics = ClassificationMetrics(targets, predictions, categorical=True)


class test_errors(unittest.TestCase):

    def test_radial_pots(self):
        plot_metrics(all_errors, plot_type='bar', max_metrics_per_fig=50, save_path=os.path.join(os.getcwd(), "results"))
        plot_metrics(all_errors, plot_type='radial', save_path=os.path.join(os.getcwd(), "results"))
        return

    def test_attrs(self):
        for _attr in not_metrics:
            assert _attr not in er.all_methods

    def test_calculate_all(self):
        assert len(all_errors) > 100
        for er_name, er_val in all_errors.items():
            if er_val is not None:
                er_val = getattr(er, er_name)()
                self.assertEqual(er_val.__class__.__name__, 'float', f'{er_name} is {er_val}')
        return

    def test_stats(self):
        s = er.stats()
        assert len(s) > 1.0
        return

    def test_mrae(self):
        assert er.mare() * 100.0 == er.mape()
        return

    def test_mare(self):
        # https://support.numxl.com/hc/en-us/articles/115001223363-MRAE-Mean-Relative-Absolute-Error
        data = np.array(
            [[-2.9, 	-2.95],
             [-2.83, 	-2.7],
             [-0.95, 	-1.00],
             [-0.88, 	-0.68],
             [1.21,	1.50],
             [-1.67, 	-1.00],
             [0.83, 	0.90],
             [-0.27, 	-0.37],
             [1.36, 	1.26],
             [-0.34, 	-0.54],
             [0.48, 	0.58],
             [-2.83, 	-2.13],
             [-0.95, 	-0.75],
             [-0.88, 	-0.89],
             [1.21, 	1.25],
             [-1.67, 	-1.65],
             [-2.99, 	-3.20],
             [1.24, 	1.29],
             [0.64, 	0.60]]
        )
        errs = RegressionMetrics(data[:, 0], data[:, 1])
        np.testing.assert_almost_equal(0.348, errs.mrae(), 2)
        assert errs.mare() * 100.0 == errs.mape()
        return

    def test_ce(self):
        # https://stackoverflow.com/a/47398312/5982232
        self.assertAlmostEqual(class_metrics.cross_entropy(), 0.71355817782)
        return

    def test_class_all(self):
        all_metrics = class_metrics.calculate_all()
        assert len(all_metrics) > 1
        return

    def test_hydro_metrics(self):
        hydr_metrics = er.calculate_hydro_metrics()
        assert len(hydr_metrics) == len(er._hydro_metrics())
        return

    def test_minimal(self):
        minimal_metrics = er.calculate_minimal()
        assert len(minimal_metrics) == len(er._minimal())
        return

    def test_scale_dependent(self):
        minimal_metrics = er.calculate_scale_dependent_metrics()
        assert len(minimal_metrics) == len(er._scale_dependent_metrics())
        return

    def test_scale_independent(self):
        minimal_metrics = er.calculate_scale_independent_metrics()
        assert len(minimal_metrics) == len(er._scale_independent_metrics())
        return

    def test_list_subclass_methods(self):
        class DP:
            def _pa(self): pass

        class D(DP):
            def a(self): pass
            def _a(self): pass
            def b(self): pass

        self.assertEqual(len(list_subclass_methods(D, True)), 2)
        self.assertEqual(len(list_subclass_methods(D, True, False)), 3)
        self.assertEqual(len(list_subclass_methods(D, True, False, ['b'])), 2)
        return


if __name__ == "__main__":
    unittest.main()
