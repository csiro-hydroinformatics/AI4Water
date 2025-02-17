import os
import site   # so that AI4Water directory is in path
import sys
import unittest
ai4_dir = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))
site.addsitedir(ai4_dir)

from ai4water.datasets import arg_beach, load_u1
from ai4water.pytorch_models import HARHNModel, IMVModel

lookback = 10
epochs = 50
df = arg_beach()


class TestPytorchModels(unittest.TestCase):
    def test_hrhnmodel(self):
        model = HARHNModel(data=load_u1(),
                           teacher_forcing=True,
                           epochs=3,
                           model={'layers': {'n_conv_lyrs': 3, 'enc_units': 4, 'dec_units': 4}},
                           verbosity=0
                           )
        model.fit()
        p = model.predict()
        s = model.evaluate('training')
        return

    def test_imvmodel(self):
        model = IMVModel(data=arg_beach(),
                         val_data="same",
                         val_fraction=0.0,
                         epochs=2,
                         lr=0.0001,
                         batch_size=4,
                         train_data='random',
                         transformation=[
                             {'method': 'minmax', 'features': list(arg_beach().columns)[0:-1]},
                             {'method': 'log2', 'features': ['tetx_coppml'], 'replace_zeros': True, 'replace_nans': True}
                         ],
                         model={'layers': {'hidden_units': 4}},
                         verbosity=0
                         )

        model.fit()
        model.predict()
        model.evaluate('training')
        model.interpret()

if __name__ == "__main__":
    unittest.main()