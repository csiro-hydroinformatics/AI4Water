import os
import sys
import site
import unittest
ai4_dir = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))
site.addsitedir(ai4_dir)

import numpy as np

from ai4water.eda import EDA
from ai4water.eda.utils import pac_yw, auto_corr, ccovf_np, ccf_np
from ai4water.datasets import MtropicsLaos, arg_beach

laos = MtropicsLaos()

pcp = laos.fetch_pcp(
    st="20110101", en="20110104"
)


class TestEDA(unittest.TestCase):

    def test_series(self):
        eda = EDA(data=pcp, save=False, show=False)
        eda()
        return

    def test_dataframe(self):
        eda = EDA(data=arg_beach(), dpi=50, save=False, show=False)
        eda()
        return

    def test_with_input_features(self):
        eda = EDA(
            data=arg_beach(), in_cols=arg_beach().columns.to_list()[0:-1],
            dpi=50,
            save=False,
            show=False)
        eda()
        return

    def test_autocorr(self):

        eda = EDA(data=arg_beach(), path=os.path.join(os.getcwd(), "results"), save=False, show=False)
        eda.autocorrelation(nlags=10)
        return

    def test_partial_autocorr(self):
        eda = EDA(data=arg_beach(), path=os.path.join(os.getcwd(), "results"), save=False, show=False)
        eda.partial_autocorrelation(nlags=10)
        return

    def test_autocorr_against_statsmodels(self):
        try:
            from statsmodels.tsa.stattools import acf, pacf
        except (ModuleNotFoundError, ImportError):
            acf, pacf = None, None

        if acf is not None:
            a = np.sin(np.linspace(0, 20, 100))

            np.testing.assert_allclose(acf(a, nlags=4), auto_corr(a, 4))
            np.testing.assert_allclose(pacf(a, nlags=4), pac_yw(a, 4))

        return

    def test_cross_corr_against_statsmodels(self):
        try:
            from statsmodels.tsa.stattools import ccf, ccovf
        except (ModuleNotFoundError, ImportError):
            ccf, ccovf = None, None

        if ccf is not None:
            a = np.linspace(0, 40, 100)
            b = np.sin(a)
            c = np.cos(b)

            np.allclose(ccf(b, c), ccf_np(b, c))

            np.allclose(ccovf_np(b, c), ccovf(b, c).sum())

        return

if __name__ == "__main__":

    unittest.main()