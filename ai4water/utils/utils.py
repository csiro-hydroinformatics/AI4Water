import os
import json
import pprint
import datetime
import warnings
from typing import Union
from shutil import rmtree
from copy import deepcopy
from typing import Any, Dict, Tuple
from collections import OrderedDict
import collections.abc as collections_abc

import scipy
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.stats import skew, kurtosis, variation, gmean, hmean

try:
    import wrapt
except ModuleNotFoundError:
    wrapt = None


def reset_seed(seed: Union[int, None], os=None, random=None, np=None, tf=None, torch=None):
    """
    Sets the random seed for a given module if the module is not None
    Arguments:
        seed : Value of seed to set. If None, then it means we don't wan't to set
        the seed.
        os : alias for `os` module of python
        random : alias for `random` module of python
        np : alias for `numpy` module
        tf : alias for `tensorflow` module.
        torch : alias for `pytorch` module.
        """
    if seed:
        if np:
            np.random.seed(seed)

        if random:
            random.seed(seed)

        if os:
            os.environ['PYTHONHASHSEED'] = str(seed)

        if tf:
            if int(tf.__version__.split('.')[0]) == 1:
                tf.compat.v1.random.set_random_seed(seed)
            elif int(tf.__version__.split('.')[0]) > 1:
                tf.random.set_seed(seed)

        if torch:
            torch.manual_seed(seed)
            torch.cuda.manual_seed(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = True
    return


def maybe_create_path(prefix=None, path=None):
    if path is None:
        save_dir = dateandtime_now()
        model_dir = os.path.join(os.getcwd(), "results")

        if prefix:
            model_dir = os.path.join(model_dir, prefix)

        save_dir = os.path.join(model_dir, save_dir)
    else:
        save_dir = path

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    for _dir in ['activations', 'weights', 'data']:
        if not os.path.exists(os.path.join(save_dir, _dir)):
            os.makedirs(os.path.join(save_dir, _dir))

    return save_dir


def dateandtime_now() -> str:
    """
    Returns the datetime in following format as string
    YYYYMMDD_HHMMSS
    """
    jetzt = datetime.datetime.now()
    dt = ''
    for time in ['year', 'month', 'day', 'hour', 'minute', 'second']:
        _time = str(getattr(jetzt, time))
        if len(_time) < 2:
            _time = '0' + _time
        if time == 'hour':
            _time = '_' + _time
        dt += _time
    return dt


def save_config_file(path, config=None, errors=None, indices=None, others=None, name=''):

    sort_keys = True
    if errors is not None:
        suffix = dateandtime_now()
        fpath = path + "/errors_" + name + suffix + ".json"
        # maybe some errors are not json serializable.
        for er_name, er_val in errors.items():
            if "int" in er_val.__class__.__name__:
                errors[er_name] = int(er_val)
            elif "float" in er_val.__class__.__name__:
                errors[er_name] = float(er_val)

        data = errors
    elif config is not None:
        fpath = path + "/config.json"
        data = config
        sort_keys = False
    elif indices is not None:
        fpath = path + "/indices.json"
        data = indices
    else:
        assert others is not None
        data = others
        fpath = path

    if 'config' in data:
        if data['config'].get('model', None) is not None:
            model = data['config']['model']
            if 'layers' not in model:  # because ML args which come algorithms may not be of json serializable.
                model = Jsonize(model)()
                data['config']['model'] = model

    with open(fpath, 'w') as fp:
        json.dump(data, fp, sort_keys=sort_keys, indent=4, cls=JsonEncoder)

    return


def check_min_loss(epoch_losses, epoch, msg: str, save_fg: bool, to_save=None):
    epoch_loss_array = epoch_losses[:-1]

    current_epoch_loss = epoch_losses[-1]

    if len(epoch_loss_array) > 0:
        min_loss = np.min(epoch_loss_array)
    else:
        min_loss = current_epoch_loss

    if np.less(current_epoch_loss, min_loss):
        msg = msg + "    {:10.5f} ".format(current_epoch_loss)

        if to_save is not None:
            save_fg = True
    else:
        msg = msg + "              "

    return msg, save_fg


def check_kwargs(**kwargs):

    # If learning rate for XGBoost is not provided use same as default for NN
    lr = kwargs.get("lr", 0.001)
    if kwargs.get('model', None) is not None:
        model = kwargs['model']
        if 'layers' not in model:
            # for case when model='randomforestregressor'
            if isinstance(model, str):
                model = {model: {}}
                kwargs['model'] = model

            if list(model.keys())[0].startswith("XGB"):
                if "learning_rate" not in model:
                    kwargs["model"]["learning_rate"] = lr

            if "batches" not in kwargs:  # for ML, default batches will be 2d unless the user specifies otherwise.
                kwargs["batches"] = "2d"

            if "lookback" not in kwargs:
                kwargs["lookback"] = 1

    return kwargs


class make_model(object):

    def __init__(self, **kwargs):

        self.config, self.data_config = _make_model(**kwargs)


def process_io(**kwargs):

    input_features = kwargs.get('input_features', None)
    output_features = kwargs.get('output_features', None)

    if isinstance(input_features, str):
        input_features = [input_features]
    if isinstance(output_features, str):
        output_features = [output_features]

    kwargs['input_features'] = input_features
    kwargs['output_features'] = output_features
    return kwargs


def _make_model(**kwargs):
    """
    This functions fills the default arguments needed to run all the models.
    All the input arguments can be overwritten
    by providing their name.
    :return
      nn_config: `dict`, contais parameters to build and train the neural network
        such as `layers`
      data_config: `dict`, contains parameters for data preparation/pre-processing/post-processing etc.
    """
    kwargs = process_io(**kwargs)

    kwargs = check_kwargs(**kwargs)

    def_mode = "regression"  # default mode
    model = kwargs.get('model', None)
    def_cat = None

    if model is not None:
        if 'layers' in model:
            def_cat = "DL"
            # for DL, the default mode case will be regression
        else:
            if list(model.keys())[0].upper().endswith("CLASSIFIER"):
                def_mode = "classification"
            def_cat = "ML"

    if 'loss' in kwargs:
        if callable(kwargs['loss']) and hasattr(kwargs['loss'], 'name'):
            loss_name = kwargs['loss'].name
        else:
            loss_name = kwargs['loss']
        if loss_name in [
            'sparse_categorical_crossentropy',
            'categorical_crossentropy',
            'binary_crossentropy'
        ]:
            def_mode = 'classification'

    accept_additional_args = False
    if 'accept_additional_args' in kwargs:
        accept_additional_args = kwargs.pop('accept_additional_args')

    model_args = {

        'model': {'type': dict, 'default': None, 'lower': None, 'upper': None, 'between': None},
        # for auto-encoders
        'composite':    {'type': bool, 'default': False, 'lower': None, 'upper': None, 'between': None},
        'lr':           {'type': float, 'default': 0.001, 'lower': None, 'upper': None, 'between': None},
        # can be any of valid keras optimizers https://www.tensorflow.org/api_docs/python/tf/keras/optimizers
        'optimizer':    {'type': str, 'default': 'adam', 'lower': None, 'upper': None, 'between': None},
        'loss':         {'type': [str, 'callable'], 'default': 'mse', 'lower': None, 'upper': None, 'between': None},
        'quantiles':    {'type': list, 'default': None, 'lower': None, 'upper': None, 'between': None},
        'epochs':       {'type': int, 'default': 14, 'lower': None, 'upper': None, 'between': None},
        'min_val_loss': {'type': float, 'default': 0.0001, 'lower': None, 'upper': None, 'between': None},
        'patience':     {'type': int, 'default': 100, 'lower': None, 'upper': None, 'between': None},
        'shuffle':      {'type': bool, 'default': True, 'lower': None, 'upper': None, 'between': None},
        # to save the best models using checkpoints
        'save_model':   {'type': bool, 'default': True, 'lower': None, 'upper': None, 'between': None},
        # used for cnn_lst structure
        'subsequences': {'type': int, 'default': 3, 'lower': 2, "upper": None, "between": None},

        'backend':       {'type': str, 'default': 'tensorflow', 'lower': None, 'upper': None,
                          'between': ['tensorflow', 'pytorch']},
        # buffer_size is only relevant if 'val_data' is same and shuffle is true.
        # https://www.tensorflow.org/api_docs/python/tf/data/Dataset#shuffle
        # It is used to shuffle tf.Dataset of training data.
        'buffer_size': {'type': int, 'default': 100, 'lower': None, 'upper': None, 'between': None},
        # comes handy if we want to skip certain batches from last
        'batches_per_epoch': {"type": int, "default": None, 'lower': None, 'upper': None, 'between': None},
        # https://www.tensorflow.org/api_docs/python/tf/keras/Model#fit
        'steps_per_epoch': {"type": int, "default": None, 'lower': None, 'upper': None, 'between': None},
        # can be string or list of strings such as 'mse', 'kge', 'nse', 'pbias'
        'metrics': {"type": list, "default": ['nse'], 'lower': None, 'upper': None, 'between': None},
        # if true, model will use previous predictions as input  # todo, where it is used?
        'use_predicted_output': {"type": bool, "default": True, 'lower': None, 'upper': None, 'between': None},
        # todo, is it  redundant?
        # If the model takes one kind of input_features that is it consists of
        # only 1 Input layer, then the shape of the batches
        # will be inferred from the Input layer but for cases, the model takes more than 1 Input, then there can be two
        # cases, either all the input_features are of same shape or they
        # are not. In second case, we should overwrite `train_paras`
        # method. In former case, define whether the batches are 2d or 3d. 3d means it is for an LSTM and 2d means it is
        # for Dense layer.
        'batches': {"type": str, "default": '3d', 'lower': None, 'upper': None, 'between': ["2d", "3d"]},
        'prefix': {"type": str, "default": None, 'lower': None, 'upper': None, 'between': None},
        'path': {"type": str, "default": None, 'lower': None, 'upper': None, 'between': None},
        'kmodel': {'type': None, "default": None, 'lower': None, 'upper': None, 'between': None},
        'cross_validator': {'default': None, 'between': ['LeaveOneOut', 'kfold']},
        'wandb_config': {'type': dict, 'default': None, 'between': None},
        'val_metric': {'type': str, 'default': 'mse'}
    }

    data_args = {
        # if the shape of last batch is smaller than batch size and if we
        # want to skip this last batch, set following to True.
        # Useful if we have fixed batch size in our model but the number of samples is not fully divisble by batch size
        'drop_remainder': {"type": bool, "default": False, 'lower': None, 'upper': None, 'between': [True, False]},
        'category': {'type': str, 'default': def_cat, 'lower': None, 'upper': None, 'between': ["ML", "DL"]},
        'mode': {'type': str, 'default': def_mode, 'lower': None, 'upper': None,
                    'between': ["regression", "classification"]},
        # how many future values we want to predict
        'forecast_len':   {"type": int, "default": 1, 'lower': 1, 'upper': None, 'between': None},
        # can be None or any of the method defined in ai4water.utils.transformatinos.py
        'transformation':         {"type": [str, type(None), dict, list],   "default": None, 'lower': None,
                                   'upper': None, 'between': None},
        # The term lookback has been adopted from Francois Chollet's
        # "deep learning with keras" book. This means how many
        # historical time-steps of data, we want to feed to at time-step to predict next value. This value must be one
        # for any non timeseries forecasting related problems.
        'lookback':          {"type": int,   "default": 15, 'lower': 1, 'upper': None, 'between': None},
        'batch_size':        {"type": int,   "default": 32, 'lower': None, 'upper': None, 'between': None},
        'train_data': {'type': None, 'default': None, 'lower': None, 'upper': None, 'between': None},
        # fraction of data to be used for validation
        'val_fraction':      {"type": float, "default": 0.2, 'lower': None, 'upper': None, 'between': None},
        # the following argument can be set to 'same' for cases if you want to use same data as validation as well as
        # test data. If it is 'same', then same fraction/amount of data will be used for validation and test.
        # If this is not string and not None, this will overwite `val_fraction`
        'val_data':          {"type": None,  "default": None, 'lower': None, 'upper': None, 'between': ["same", None]},
        # fraction of data to be used for test
        'test_fraction':     {"type": float, "default": 0.2, 'lower': None, 'upper': None, 'between': None},
        # write the data/batches as hdf5 file
        'save':        {"type": bool,  "default": False, 'lower': None, 'upper': None, 'between': None},
        'allow_nan_labels':       {"type": int,  "default": 0, 'lower': 0, 'upper': 2, 'between': None},

        'nan_filler':        {"type": None, "default": None, "lower": None, "upper": None, "between": None},

        # for reproducability
        'seed':              {"type": None, "default": 313, 'lower': None, 'upper': None, 'between': None},
        # how many steps ahead we want to predict
        'forecast_step':     {"type": int, "default": 0, 'lower': 0, 'upper': None, 'between': None},
        # step size of input data
        'input_step':        {"type": int, "default": 1, 'lower': 1, 'upper': None, 'between': None},
        # whether to use future input data for multi horizon prediction or not
        'known_future_inputs': {'type': bool, 'default': False, 'lower': None, 'upper': None, 'between': [True, False]},
        # input features in data_frame
        'input_features':            {"type": None, "default": None, 'lower': None, 'upper': None, 'between': None},
        # column in dataframe to bse used as output/target
        'output_features':           {"type": None, "default": None, 'lower': None, 'upper': None, 'between': None},
        # tuple of tuples where each tuple consits of two integers, marking the start and end
        # of interval. An interval here
        # means chunk/rows from the input file/dataframe to be skipped when when preparing
        # data/batches for NN. This happens
        # when we have for example some missing values at some time in our data.
        # For further usage see `examples/using_intervals`
        "intervals":         {"type": None, "default": None, 'lower': None, 'upper': None, 'between': None},
        'verbosity':         {"type": int, "default": 1, 'lower': None, 'upper': None, 'between': None},
        'teacher_forcing': {'type': bool, 'default': False, 'lower': None, 'upper': None, 'between': [True, False]},
        'dataset_args' : {'type': dict, 'default': {}}
    }

    model_config=  {key:val['default'] for key,val in model_args.items()}

    config = {key:val['default'] for key,val in data_args.items()}

    for key, val in kwargs.items():
        arg_name = key.lower()  # todo, why this?

        if arg_name in model_config:
            update_dict(arg_name, val, model_args, model_config)

        elif arg_name in config:
            update_dict(arg_name, val, data_args, config)

        # config may contain additional user defined args which will not be checked
        elif not accept_additional_args:
            raise ValueError(f"Unknown keyworkd argument '{key}' provided")
        else:
            config[key] = val

    if config['allow_nan_labels'] > 0:
        assert 'layers' in model_config['model'], f"""
The model appears to be deep learning based because 
the argument `model` does not have layers. But you are
allowing nan labels in the targets.
However, `allow_nan_labels` should be > 0 only for deep learning models
"""

    config.update(model_config)

    if isinstance(config['input_features'], dict):
        for data in [config['input_features'], config['output_features']]:
            for k,v in data.items():
                assert isinstance(v, list), f"{k} is of type {v.__class__.__name__} but it must of of type list"

    _data_config = {}
    for key, val in config.items():
        if key in data_args:
            _data_config[key] = val

    return config, _data_config


def update_dict(key, val, dict_to_lookup, dict_to_update):
    """Updates the dictionary with key, val if the val is of type dtype."""
    dtype = dict_to_lookup[key].get('type', None)
    low = dict_to_lookup[key].get('lower', None)
    up = dict_to_lookup[key].get('upper', None)
    between = dict_to_lookup[key].get('between', None)

    if dtype is not None:
        if isinstance(dtype, list):
            val_type = type(val)
            if 'callable' in dtype:
                if callable(val):
                    pass

            elif val_type not in dtype:
                raise TypeError("{} must be any of the type {} but it is of type {}"
                                .format(key, dtype, val.__class__.__name__))
        elif not isinstance(val, dtype):
            if val != dict_to_lookup[key]['default']: # the default value may be None which will be different than dtype
                raise TypeError(f"{key} must be of type {dtype} but it is of type {val.__class__.__name__}")

    if isinstance(val, int) or isinstance(val, float):
        if low is not None:
            if val < low:
                raise ValueError(f"The value '{val}' for '{key}' must be greater than '{low}'")
        if up is not None:
            if val > up:
                raise ValueError(f"The value '{val} for '{key} must be less than '{up}'")

    if isinstance(val, str):
        if between is not None:
            if val not in between:
                raise ValueError(f"Unknown value '{val}' for '{key}'. It must be one of '{between}'")

    dict_to_update[key] = val
    return


def to_datetime_index(idx_array, fmt='%Y%m%d%H%M') -> pd.DatetimeIndex:
    """ converts a numpy 1d array into pandas DatetimeIndex type."""

    if not isinstance(idx_array, np.ndarray):
        raise TypeError

    idx = pd.to_datetime(idx_array.astype(str), format=fmt)
    idx.freq = pd.infer_freq(idx)
    return idx


class Jsonize(object):
    """Converts the objects to json compatible format i.e to native python types.
    If the object is sequence then each member of the sequence is checked and
    converted if needed. Same goes for nested sequences like lists of lists
    or list of dictionaries.

    Examples:
    ---------
    >>>import numpy as np
    >>>from ai4water.utils.utils import Jsonize
    >>>a = np.array([2.0])
    >>>b = Jsonize(a)(a)
    >>>type(b)  # int
    """
    # TODO, repeating code in __call__ and stage2
    # TODO, stage2 not considering tuple

    def __init__(self, obj):
        self.obj = obj

    def __call__(self):
        """Serializes one object"""
        if 'int' in self.obj.__class__.__name__:
            return int(self.obj)
        if 'float' in self.obj.__class__.__name__:
            return float(self.obj)

        if isinstance(self.obj, dict):
            return {k: self.stage2(v) for k, v in self.obj.items()}

        if hasattr(self.obj, '__len__') and not isinstance(self.obj, str):
            return [self.stage2(i) for i in self.obj]

        # if obj is a python 'type'
        if type(self.obj).__name__ == type.__name__:
            return self.obj.__name__

        if isinstance(self.obj, collections_abc.Mapping):
            return dict(self.obj)

        if self.obj is Ellipsis:
            return {'class_name': '__ellipsis__'}

        if wrapt and  isinstance(self.obj, wrapt.ObjectProxy):
            return self.obj.__wrapped__

        return str(self.obj)

    def stage2(self, obj):
        """Serializes one object"""
        if any([isinstance(obj, _type) for _type in [bool, set, type(None)]]) or callable(obj):
            return obj

        if 'int' in obj.__class__.__name__:
            return int(obj)

        if 'float' in obj.__class__.__name__:
            return float(obj)

        # tensorflow tensor shape
        if obj.__class__.__name__ == 'TensorShape':
            return obj.as_list()

        if isinstance(obj, dict):  # iterate over obj until it is a dictionary
            return {k: self.stage2(v) for k, v in obj.items()}

        if hasattr(obj, '__len__') and not isinstance(obj, str):
            if len(obj) > 1:  # it is a list like with length greater than 1
                return [self.stage2(i) for i in obj]
            elif isinstance(obj, list) and len(obj) > 0:  # for cases like obj is [np.array([1.0])] -> [1.0]
                return [self.stage2(obj[0])]
            elif len(obj) == 1:  # for cases like obj is np.array([1.0])
                if isinstance(obj, list) or isinstance(obj, tuple):
                    return obj  # for cases like (1, ) or [1,]
                return self.stage2(obj[0])
            else: # when object is []
                return obj

        # if obj is a python 'type'
        if type(obj).__name__ == type.__name__:
            return obj.__name__

        if obj is Ellipsis:
            return {'class_name': '__ellipsis__'}

        if wrapt and isinstance(obj, wrapt.ObjectProxy):
            return obj.__wrapped__

        # last solution, it must be of of string type
        return str(obj)


def jsonize(obj):
    """functional interface to `Jsonize` class"""
    return Jsonize(obj)()


def make_hpo_results(opt_dir, metric_name='val_loss') -> dict:
    """Looks in opt_dir and saves the min val_loss with the folder name"""
    results = {}
    for folder in os.listdir(opt_dir):
        fname = os.path.join(os.path.join(opt_dir, folder), 'losses.csv')

        if os.path.exists(fname):
            df = pd.read_csv(fname)

            if 'val_loss' in df:
                min_val_loss = round(float(np.nanmin(df[metric_name])), 6)
                results[min_val_loss] = {'folder': os.path.basename(folder)}
    return results


def find_best_weight(w_path: str, best: str = "min", ext: str = ".hdf5", epoch_identifier: int = None):
    """Given weights in w_path, find the best weight.
    if epoch_identifier is given, it will be given priority to find best_weights
    The file_names are supposed in following format FileName_Epoch_Error.ext

    Note: if we are monitoring more than two metrics whose desired behaviour
        is opposite to each other then this method does not work as desired. However
        this can be avoided by specifying `epoch_identifier`.
    """
    assert best in ['min', 'max']
    all_weights = os.listdir(w_path)

    if len(all_weights)==1:
        return all_weights[0]

    losses = {}
    for w in all_weights:
        wname = w.split(ext)[0]
        val_loss = str(float(wname.split('_')[2]))  # converting to float so that trailing 0 is removed
        losses[val_loss] = {'loss': wname.split('_')[2], 'epoch': wname.split('_')[1]}

    best_weight = None
    if epoch_identifier:
        for v in losses.values():
            if str(epoch_identifier) in v['epoch']:
                best_weight = f"weights_{v['epoch']}_{v['loss']}.hdf5"
                break

    else:
        loss_array = np.array([float(l) for l in losses.keys()])
        if len(loss_array) == 0:
            return None
        best_loss = getattr(np, best)(loss_array)
        best_weight = f"weights_{losses[str(best_loss)]['epoch']}_{losses[str(best_loss)]['loss']}.hdf5"

    return best_weight


def remove_all_but_best_weights(w_path, best: str = "min", ext: str = ".hdf5"):
    """removes all the weights from a folder except the best weigtht"""
    best_weights = None
    if os.path.exists(w_path):
        # remove all but best weight
        all_weights = os.listdir(w_path)
        best_weights = find_best_weight(w_path, best=best, ext=ext)
        ws_to_del = [w for w in all_weights if w != best_weights]
        for w in ws_to_del:
            os.remove(os.path.join(w_path, w))

    return best_weights


def clear_weights(opt_dir, results: dict = None, keep=3, rename=True, write=True):
    """Optimization will save weights of all the trained models, not all of them
    are useful. Here removing weights of all except top 3. The number of models
    whose weights to be retained can be set by `keep` para.
    """
    fname = 'sorted.json'
    if results is None:
        results = make_hpo_results(opt_dir)
        fname = 'sorted_folders.json'

    od = OrderedDict(sorted(results.items()))

    idx = 0
    best_results = {}

    for v in od.values():
        if 'folder' in v:
            folder = v['folder']
            _path = os.path.join(opt_dir, folder)
            w_path = os.path.join(_path, 'weights')

            if idx > keep-1:
                if os.path.exists(w_path):
                    rmtree(w_path)
            else:
                best_weights = remove_all_but_best_weights(w_path)
                best_results[folder] = {'path': _path, 'weights': best_weights}

            idx += 1

    if rename:
        # append ranking of models to folder_names
        idx = 0
        for v in od.values():
            if 'folder' in v:
                folder = v['folder']
                old_path = os.path.join(opt_dir, folder)
                new_path = os.path.join(opt_dir, str(idx+1) + "_" + folder)
                os.rename(old_path, new_path)

                if folder in best_results:
                    best_results[folder] = {'path': new_path, 'weights': best_results[folder]}

                idx += 1

    od = {k: Jsonize(v)() for k, v in od.items()}

    if write:
        sorted_fname = os.path.join(opt_dir, fname)
        with open(sorted_fname, 'w') as sfp:
            json.dump(od, sfp, sort_keys=True, indent=True)

    return best_results


def train_val_split(x, y, validation_split):
    if hasattr(x[0], 'shape'):
        # x is list of arrays
        # assert that all arrays are of equal length
        split_at = int(x[0].shape[0] * (1. - validation_split))
    else:
        split_at = int(len(x[0]) * (1. - validation_split))

    x, val_x = (slice_arrays(x, 0, split_at), slice_arrays(x, split_at))
    y, val_y = (slice_arrays(y, 0, split_at), slice_arrays(y, split_at))

    return x, y, val_x, val_y


def slice_arrays(arrays, start, stop=None):
    if isinstance(arrays, list):
        return [array[start:stop] for array in arrays]
    elif hasattr(arrays, 'shape'):
        return arrays[start:stop]


def split_by_indices(x, y, indices):
    """Slices the x and y arrays or lists of arrays by the indices"""

    def split_with_indices(data):
        if isinstance(data, list):
            _data = []

            for d in data:
                assert isinstance(d, np.ndarray)
                _data.append(d[indices])
        else:
            assert isinstance(data, np.ndarray)
            _data = data[indices]
        return _data

    x = split_with_indices(x)
    y = split_with_indices(y)

    return x, y


def ts_features(data: Union[np.ndarray, pd.DataFrame, pd.Series],
                precision: int = 3,
                name: str = '',
                st: int = 0,
                en: int = None,
                features: Union[list, str] = None
                ) -> dict:
    """
    Extracts features from 1d time series data. Features can be
        * point, one integer or float point value for example mean
        * 1D, 1D array for example sin(data)
        * 2D, 2D array for example wavelent transform
    Arguments:
        Gets all the possible stats about an array like object `data`.
        data: array like
        precision: number of significant figures
        name: str, only for erro or warning messages
        st: str/int, starting index of data to be considered.
        en: str/int, end index of data to be considered.
        features: name/names of features to extract from data.
    # information holding degree
    """
    point_features = {
        'Skew': skew,
        'Kurtosis': kurtosis,
        'Mean': np.nanmean,
        'Geometric Mean': gmean,
        'Standard error of mean': scipy.stats.sem,
        'Median': np.nanmedian,
        'Variance': np.nanvar,
        'Coefficient of Variation': variation,
        'Std': np.nanstd,
        'Non Zeros': np.count_nonzero,
        'Min': np.nanmin,
        'Max': np.nanmax,
        'Sum': np.nansum,
        'Counts': np.size
    }

    point_features_lambda = {
        'Shannon entropy': lambda x: np.round(scipy.stats.entropy(pd.Series(x).value_counts()), precision),
        'Negative counts': lambda x: int(np.sum(x < 0.0)),
        '90th percentile': lambda x: np.round(np.nanpercentile(x, 90), precision),
        '75th percentile': lambda x: np.round(np.nanpercentile(x, 75), precision),
        '50th percentile': lambda x: np.round(np.nanpercentile(x, 50), precision),
        '25th percentile': lambda x: np.round(np.nanpercentile(x, 25), precision),
        '10th percentile': lambda x: np.round(np.nanpercentile(x, 10), precision),
    }

    if not isinstance(data, np.ndarray):
        if hasattr(data, '__len__'):
            data = np.array(data)
        else:
            raise TypeError(f"{name} must be array like but it is of type {data.__class__.__name__}")

    if np.array(data).dtype.type is np.str_:
        warnings.warn(f"{name} contains string values")
        return {}

    if 'int' not in data.dtype.name:
        if 'float' not in data.dtype.name:
            warnings.warn(f"changing the dtype of {name} from {data.dtype.name} to float")
            data = data.astype(np.float64)

    assert data.size == len(data), f"""
data must be 1 dimensional array but it has shape {np.shape(data)}
"""
    data = data[st:en]
    stats = dict()

    if features is None:
        features = list(point_features.keys()) + list(point_features_lambda.keys())
    elif isinstance(features, str):
        features = [features]

    for feat in features:
        if feat in point_features:
            stats[feat] = np.round(point_features[feat](data), precision)
        elif feat in point_features_lambda:
            stats[feat] = point_features_lambda[feat](data)

    if 'Harmonic Mean' in features:
        try:
            stats['Harmonic Mean'] = np.round(hmean(data), precision)
        except ValueError:
            warnings.warn(f"""Unable to calculate Harmonic mean for {name}. Harmonic mean only defined if all
                          elements are greater than or equal to zero""", UserWarning)

    return Jsonize(stats)()


def _missing_vals(data: pd.DataFrame) -> Dict[str, Any]:
    """
    Modified after https://github.com/akanz1/klib/blob/main/klib/utils.py#L197
     Gives metrics of missing values in the dataset.
    Parameters
    ----------
    data : pd.DataFrame
        2D dataset that can be coerced into Pandas DataFrame
    Returns
    -------
    Dict[str, float]
        mv_total: float, number of missing values in the entire dataset
        mv_rows: float, number of missing values in each row
        mv_cols: float, number of missing values in each column
        mv_rows_ratio: float, ratio of missing values for each row
        mv_cols_ratio: float, ratio of missing values for each column
    """

    data = pd.DataFrame(data).copy()
    mv_rows = data.isna().sum(axis=1)
    mv_cols = data.isna().sum(axis=0)
    mv_total = data.isna().sum().sum()
    mv_rows_ratio = mv_rows / data.shape[1]
    mv_cols_ratio = mv_cols / data.shape[0]

    return {
        "mv_total": mv_total,
        "mv_rows": mv_rows,
        "mv_cols": mv_cols,
        "mv_rows_ratio": mv_rows_ratio,
        "mv_cols_ratio": mv_cols_ratio,
    }


def prepare_data(
        data: np.ndarray,
        lookback_steps: int,
        num_inputs: int = None,
        num_outputs: int = None,
        input_steps: int = 1,
        forecast_step: int = 0,
        forecast_len: int = 1,
        known_future_inputs: bool = False,
        output_steps=1,
        mask: Union[int, float, np.ndarray] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    converts a numpy nd array into a supervised machine learning problem.

    Arguments:
        data np.ndarray :
            nd numpy array whose first dimension represents the number
            of examples and the second dimension represents the number of features.
            Some of those features will be used as inputs and some will be considered
            as outputs depending upon the values of `num_inputs` and `num_outputs`.
        lookback_steps int :
            number of previous steps/values to be used at one step.
        num_inputs int :
            default None, number of input features in data. If None,
            it will be calculated as features-outputs. The input data will be all
            from start till num_outputs in second dimension.
        num_outputs int :
            number of columns (from last) in data to be used as output.
            If None, it will be caculated as features-inputs.
        input_steps int :
            strides/number of steps in input data
        forecast_step int :
            must be greater than equal to 0, which t+ith value to
            use as target where i is the horizon. For time series prediction, we
            can say, which horizon to predict.
        forecast_len int :
            number of horizons/future values to predict.
        known_future_inputs bool : Only useful if `forecast_len`>1. If True, this
            means, we know and use 'future inputs' while making predictions at t>0
        output_steps int :
            step size in outputs. If =2, it means we want to predict
            every second value from the targets
        mask int/np.nan/1darray :
            If int, then the examples with these values in
            the output will be skipped. If array then it must be a boolean mask
            indicating which examples to include/exclude. The length of mask should
            be equal to the number of generated examples. The number of generated
            examples is difficult to prognose because it depend upon lookback, input_steps,
            and forecast_step. Thus it is better to provide an integer indicating
            which values in outputs are to be considered as invalid. Default is
            None, which indicates all the generated examples will be returned.

    Returns:
      x : numpy array of shape (examples, lookback, ins) consisting of
        input examples
      prev_y : numpy array consisting of previous outputs
      y : numpy array consisting of target values

    Given following data consisting of input/output pairs

    |input1 | input2 | output1 | output2 | output 3 |
    |-------|--------|---------|---------|----------|
    |   1  |   11  |   21   |    31  |   41 |
    |   2  |   12  |   22   |    32  |   42 |
    |   3  |   13  |   23   |    33  |   43 |
    |   4  |   14  |   24   |    34  |   44 |
    |   5  |   15  |   25   |    35  |   45 |
    |   6  |   16  |   26   |    36  |   46 |
    |   7  |   17  |   27   |    37  |   47 |

    If we use following 2 time series as input

    |input1 | input2 |
    |----|-----|
    | 1  |  11 |
    | 2  |  12 |
    | 3  |  13 |
    | 4  |  14 |
    | 5  |  15 |
    | 6  |  16 |
    | 7  |  17 |

    then  `num_inputs`=2, `lookback`=7, `input_steps`=1

    and if we want to predict

    | output1 | output2 | output 3 |
    |---------|---------|----------|
    |   27    |   37    |   47     |

    then `num_outputs`=3, `forecast_len`=1,  `forecast_step`=0,

    if we want to predict

    | output1 | output2 | output 3 |
    |---------|---------|----------|
    |28 | 38 | 48 |

    then `num_outputs`=3, `forecast_len`=1,  `forecast_step`=1,

    if we want to predict predict

    | output1 | output2 | output 3 |
    |---------|---------|----------|
    | 27 | 37 | 47 |
    | 28 | 38 | 48 |

    then `num_outputs`=3, forecast_len=2,  horizon/forecast_step=0,

    if we want to predict

    | output1 | output2 | output 3 |
    |---------|---------|----------|
    | 28 | 38 | 48 |
    | 29 | 39 | 49 |
    | 30 | 40 | 50 |

    then `num_outputs`=3, `forecast_len`=3,  `forecast_step`=1,

    if we want to predict

    | output2 |
    |----------|
    | 38 |
    | 39 |
    | 40 |

    then `num_outputs`=1, `forecast_len`=3, `forecast_step`=0

    if we predict

    | output2 |
    |----------|
    | 39 |

    then `num_outputs`=1, `forecast_len`=1, `forecast_step`=2

    if we predict

    | output2 |
    |----------|
    | 39 |
    | 40 |
    | 41 |

     then `num_outputs`=1, `forecast_len`=3, `forecast_step`=2

    If we use following two time series as input

    |input1 | input2 |
    |-------|--------|
    |1 |  11 |
    |3 |  13 |
    |5 |  15 |
    |7 |  17 |

    then   `num_inputs`=2, `lookback`=4, `input_steps`=2

    If the input is

    |input1 | input2 |
    |----|-----|
    | 1 |  11 |
    | 2 |  12 |
    | 3 |  13 |
    | 4 |  14 |
    | 5 |  15 |
    | 6 |  16 |
    | 7 |  17 |

    and target/output is

    | output1 | output2 | output 3 |
    |---------|---------|----------|
    | 25 | 35 | 45 |
    | 26 | 36 | 46 |
    | 27 | 37 | 47 |

    This means we make use of 'known future inputs'. This can be achieved using following configuration
    num_inputs=2, num_outputs=3, lookback_steps=4, forecast_len=3, forecast_step=1, known_future_inputs=True

    The general shape of output/target/label is
    (examples, num_outputs, forecast_len)

    The general shape of inputs/x is
    (examples, lookback_steps+forecast_len-1, ....num_inputs)

    ----------
    Example
    ---------
    ```python
    >>>import numpy as np
    >>>from ai4water.utils.utils import prepare_data
    >>>num_examples = 50
    >>>dataframe = np.arange(int(num_examples*5)).reshape(-1, num_examples).transpose()
    >>>dataframe[0:10]
        array([[  0,  50, 100, 150, 200],
               [  1,  51, 101, 151, 201],
               [  2,  52, 102, 152, 202],
               [  3,  53, 103, 153, 203],
               [  4,  54, 104, 154, 204],
               [  5,  55, 105, 155, 205],
               [  6,  56, 106, 156, 206],
               [  7,  57, 107, 157, 207],
               [  8,  58, 108, 158, 208],
               [  9,  59, 109, 159, 209]])
    >>>x, prevy, y = prepare_data(data, num_outputs=2, lookback_steps=4,
    ...    input_steps=2, forecast_step=2, forecast_len=4)
    >>>x[0]
       array([[  0.,  50., 100.],
              [  2.,  52., 102.],
              [  4.,  54., 104.],
              [  6.,  56., 106.]], dtype=float32)
    >>>y[0]
       array([[158., 159., 160., 161.],
              [208., 209., 210., 211.]], dtype=float32)

    >>>x, prevy, y = prepare_data(data, num_outputs=2, lookback_steps=4,
    ...    forecast_len=3, known_future_inputs=True)
    >>>x[0]
        array([[  0,  50, 100],
               [  1,  51, 101],
               [  2,  52, 102],
               [  3,  53, 103],
               [  4,  54, 104],
               [  5,  55, 105],
               [  6,  56, 106]])       # (7, 3)
    >>># it is import to note that although lookback_steps=4 but x[0] has shape of 7
    >>>y[0]

        array([[154., 155., 156.],
               [204., 205., 206.]], dtype=float32)  # (2, 3)
    ```
    """
    if not isinstance(data, np.ndarray):
        if isinstance(data, pd.DataFrame):
            data = data.values
        else:
            raise TypeError(f"unknown data type for data {data.__class__.__name__}")

    if num_inputs is None and num_outputs is None:
        raise ValueError("""
Either of num_inputs or num_outputs must be provided.
""")

    features = data.shape[1]
    if num_outputs is None:
        num_outputs = features - num_inputs

    if num_inputs is None:
        num_inputs = features - num_outputs

    assert num_inputs + num_outputs == features, f"""
num_inputs {num_inputs} + num_outputs {num_outputs} != total features {features}"""

    if len(data) <= 1:
        raise ValueError(f"Can not create batches from data with shape {data.shape}")

    time_steps = lookback_steps
    if known_future_inputs:
        lookback_steps = lookback_steps + forecast_len
        assert forecast_len > 1, f"""
            known_futre_inputs should be True only when making predictions at multiple 
            horizons i.e. when forecast length/number of horizons to predict is > 1.
            known_future_inputs: {known_future_inputs}
            forecast_len: {forecast_len}"""

    examples = len(data)

    x = []
    prev_y = []
    y = []

    for i in range(examples - lookback_steps * input_steps + 1 - forecast_step - forecast_len + 1):
        stx, enx = i, i + lookback_steps * input_steps
        x_example = data[stx:enx:input_steps, 0:features - num_outputs]

        st, en = i, i + (lookback_steps - 1) * input_steps
        y_data = data[st:en:input_steps, features - num_outputs:]

        sty = (i + time_steps * input_steps) + forecast_step - input_steps
        eny = sty + forecast_len
        target = data[sty:eny, features - num_outputs:]

        x.append(np.array(x_example))
        prev_y.append(np.array(y_data))
        y.append(np.array(target))

    x = np.stack(x)
    prev_y = np.array([np.array(i, dtype=np.float32) for i in prev_y], dtype=np.float32)
    # transpose because we want labels to be of shape (examples, outs, forecast_len)
    y = np.array([np.array(i, dtype=np.float32).T for i in y], dtype=np.float32)

    if mask is not None:
        if isinstance(mask, np.ndarray):
            assert mask.ndim == 1
            assert len(x) == len(mask), f"Number of generated examples are {len(x)} " \
                                        f"but the length of mask is {len(mask)}"
        elif isinstance(mask, float) and np.isnan(mask):
            mask = np.invert(np.isnan(y))
            mask = np.array([all(i.reshape(-1,)) for i in mask])
        else:
            assert isinstance(mask, int), f"""
                    Invalid mask identifier given of type: {mask.__class__.__name__}"""
            mask = y != mask
            mask = np.array([all(i.reshape(-1,)) for i in mask])

        x = x[mask]
        prev_y = prev_y[mask]
        y = y[mask]

    return x, prev_y, y


def find_tot_plots(features, max_subplots):

    tot_plots = np.linspace(0, features, int(features / max_subplots) + 1 if features % max_subplots == 0 else int(
        features / max_subplots) + 2)
    # converting each value to int because linspace can return array containing floats if features is odd
    tot_plots = [int(i) for i in tot_plots]
    return tot_plots


def init_subplots(width=None, height=None, nrows=1, ncols=1, **kwargs):
    """Initializes the fig for subplots"""
    plt.close('all')
    fig, axis = plt.subplots(nrows=nrows, ncols=ncols, **kwargs)
    if width is not None:
        fig.set_figwidth(width)
    if height is not None:
        fig.set_figheight(height)
    return fig, axis


def process_axis(axis,
                 data: Union[list, np.ndarray, pd.Series, pd.DataFrame],
                 x: Union[list, np.ndarray] = None,  # array to plot as x
                 marker='',
                 fillstyle=None,
                 linestyle='-',
                 c=None,
                 ms=6.0,  # markersize
                 label=None,  # legend
                 leg_pos="best",
                 bbox_to_anchor=None,  # will take priority over leg_pos
                 leg_fs=12,
                 leg_ms=1,  # legend scale
                 ylim=None,  # limit for y axis
                 x_label=None,
                 xl_fs=None,
                 y_label=None,
                 yl_fs=12,  # ylabel font size
                 yl_c='k',  # y label color, if 'same', c will be used else black
                 xtp_ls=None,  # x tick_params labelsize
                 ytp_ls=None,  # x tick_params labelsize
                 xtp_c='k',  # x tick colors if 'same' c will be used else black
                 ytp_c='k',  # y tick colors, if 'same', c will be used else else black
                 log=False,
                 show_xaxis=True,
                 top_spine=True,
                 bottom_spine=True,
                 invert_yaxis=False,
                 max_xticks=None,
                 min_xticks=None,
                 title=None,
                 title_fs=None,  # title fontszie
                 log_nz=False,
                 ):

    """Purpose to act as a middle man between axis.plot/plt.plot.
    Returns:
        axis
        """
    # TODO
    # default fontsizes should be same as used by matplotlib
    # should not complicate plt.plot or axis.plto
    # allow multiple plots on same axis

    if log and log_nz:
        raise ValueError

    use_third = False
    if x is not None:
        if isinstance(x, str):  # the user has not specified x so x is currently plot style.
            style = x
            x = None
            if marker == '.':
                use_third = True

    if log_nz:
        data = deepcopy(data)
        _data = data.values
        d_nz_idx = np.where(_data > 0.0)
        data_nz = _data[d_nz_idx]
        d_nz_log = np.log(data_nz)
        _data[d_nz_idx] = d_nz_log
        _data = np.where(_data < 0.0, 0.0, _data)
        data = pd.Series(_data, index=data.index)

    if log:
        data = deepcopy(data)
        _data = np.where(data.values < 0.0, 0.0, data.values)
        print(len(_data[np.where(_data < 0.0)]))
        data = pd.Series(_data, index=data.index)

    if x is not None:
        axis.plot(x, data, fillstyle=fillstyle, color=c, marker=marker, linestyle=linestyle, ms=ms, label=label)
    elif use_third:
        axis.plot(data, style, color=c, ms=ms, label=label)
    else:
        axis.plot(data, fillstyle=fillstyle, color=c, marker=marker, linestyle=linestyle, ms=ms, label=label)

    ylc = c
    if yl_c != 'same':
        ylc = 'k'

    _kwargs = {}
    if label is not None:
        if label != "__nolabel__":
            if leg_fs is not None:
                _kwargs.update({'fontsize': leg_fs})
            if leg_ms is not None:
                _kwargs.update({'markerscale': leg_ms})
            if bbox_to_anchor is not None:
                _kwargs['bbox_to_anchor'] = bbox_to_anchor
            else:
                _kwargs['loc'] = leg_pos
            axis.legend(**_kwargs)

    if y_label is not None:
        axis.set_ylabel(y_label, fontsize=yl_fs, color=ylc)

    if log:
        axis.set_yscale('log')

    if invert_yaxis:
        axis.set_ylim(axis.get_ylim()[::-1])

    if ylim is not None:
        if not isinstance(ylim, tuple):
            raise TypeError("ylim must be tuple {} provided".format(ylim))
        axis.set_ylim(ylim)

    xtpc = c
    if xtp_c != 'same':
        xtpc = 'k'

    ytpc = c
    if ytp_c != 'same':
        ytpc = 'k'

    _kwargs = {'colors': xtpc}
    if x_label is not None or xtp_ls is not None:  # better not change these paras if user has not defined any x_label
        if xtp_ls is not None:
            _kwargs.update({'labelsize': xtp_ls})
        axis.tick_params(axis="x", which='major', **_kwargs)

    _kwargs = {'colors': ytpc}
    if y_label is not None or ytp_ls is not None:
        if ytp_ls is not None:
            _kwargs.update({'labelsize': ytp_ls})
        axis.tick_params(axis="y", which='major', **_kwargs)

    axis.get_xaxis().set_visible(show_xaxis)

    _kwargs = {}
    if x_label is not None:
        if xl_fs is not None:
            _kwargs.update({'fontsize': xl_fs})
        axis.set_xlabel(x_label, **_kwargs)

    axis.spines['top'].set_visible(top_spine)
    axis.spines['bottom'].set_visible(bottom_spine)

    if min_xticks is not None:
        assert isinstance(min_xticks, int)
        assert isinstance(max_xticks, int)
        loc = mdates.AutoDateLocator(minticks=min_xticks, maxticks=max_xticks)
        axis.xaxis.set_major_locator(loc)
        fmt = mdates.AutoDateFormatter(loc)
        axis.xaxis.set_major_formatter(fmt)

    if title_fs is None:
        title_fs = plt.rcParams['axes.titlesize']

    if title is not None:
        axis.set_title(title, fontsize=title_fs)

    return axis


def plot(*args, show=True, **kwargs):
    """
    One liner plot function. It should not be more complex than axis.plot() or
    plt.plot() yet it must accomplish all in one line what requires multiple
    lines in matplotlib. args and kwargs can be anything which goes into plt.plot()
    or axis.plot(). They can also be anything which goes into `process_axis`.
    """
    _, axis = init_subplots()
    axis = process_axis(axis, *args, **kwargs)
    if kwargs.get('save', False):
        plt.savefig(f"{kwargs.get('name', 'fig.png')}")
    if show:
        plt.show()
    return axis


class JsonEncoder(json.JSONEncoder):

    def default(self, obj):
        if 'int' in obj.__class__.__name__:
            return int(obj)
        elif 'float' in obj.__class__.__name__:
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif 'bool' in obj.__class__.__name__:
            return bool(obj)
        elif callable(obj) and hasattr(obj, '__module__'):
            return obj.__module__
        else:
            return super(JsonEncoder, self).default(obj)


def plot_activations_along_inputs(
        data: np.ndarray,
        activations: np.ndarray,
        observations: np.ndarray,
        predictions: np.ndarray,
        in_cols: list,
        out_cols: list,
        lookback: int,
        name: str,
        path: str,
        vmin=None,
        vmax=None,
        show=False
):
    # activation must be of shape (num_examples, lookback, input_features)
    assert activations.shape[1] == lookback
    assert activations.shape[2] == len(in_cols), f'{activations.shape}, {len(in_cols)}'

    # data is of shape (num_examples, input_features)
    assert data.shape[1] == len(in_cols)

    assert len(data) == len(activations)

    for out in range(len(out_cols)):
        pred = predictions[:, out]
        obs = observations[:, out]
        out_name = out_cols[out]

        for idx in range(len(in_cols)):
            plt.close('all')
            fig, (ax1, ax2, ax3) = plt.subplots(3, sharex='all')
            fig.set_figheight(12)

            ax1.plot(data[:, idx], label=in_cols[idx])
            ax1.legend()
            ax1.set_title('activations w.r.t ' + in_cols[idx])
            ax1.set_ylabel(in_cols[idx])

            ax2.plot(pred, label='Prediction')
            ax2.plot(obs, '.', label='Observed')
            ax2.legend()

            axis, im = axis_imshow(ax3, activations[:, :, idx].transpose(), lookback, vmin, vmax,
                                   xlabel="Examples")
            fig.colorbar(im, orientation='horizontal', pad=0.2)
            plt.subplots_adjust(wspace=0.005, hspace=0.005)
            _name = f'attention_weights_{out_name}_{name}'
            plt.savefig(os.path.join(path, _name) + in_cols[idx], dpi=400, bbox_inches='tight')

            if show:
                plt.show()

            plt.close('all')

    return

def axis_imshow(axis, values, lookback, vmin, vmax, xlabel=None, title=None, cmap=None):

    im = axis.imshow(values, aspect='auto', vmin=vmin, vmax=vmax, cmap=cmap)
    ytick_labels = [f"t-{int(i)}" for i in np.linspace(lookback - 1, 0, lookback)]
    axis.set_ylabel('lookback steps')
    axis.set_yticks(np.arange(len(ytick_labels)))
    axis.set_yticklabels(ytick_labels)
    if xlabel:
        axis.set_xlabel(xlabel)

    if title:
        axis.set_title(title)

    return axis, im


def print_something(something, prefix=''):
    """prints shape of some python object"""
    if isinstance(something, np.ndarray):
        print(f"{prefix} shape: ", something.shape)
    elif isinstance(something, list):
        print(f"{prefix} shape: ", [thing.shape for thing in something if isinstance(thing, np.ndarray)])
    elif isinstance(something, dict):
        print(f"{prefix} shape: ")
        pprint.pprint({k: v.shape for k, v in something.items()}, width=40)
    elif something is not None:
        print(f"{prefix} shape: ", something.shape)
        print(something)
    else:
        print(something)


def maybe_three_outputs(data, teacher_forcing=False):
    """num_outputs: how many outputs from data we want"""
    if teacher_forcing:
        num_outputs = 3
    else:
        num_outputs = 2

    if num_outputs == 2:
        if len(data) == 2:
            return data[0], data[1]
        elif len(data) == 3:
            return data[0], data[2]
    else:
        return [data[0], data[1]], data[2]

def get_version_info(
        **kwargs
)->dict:
    # todo, chekc which attributes are not available in different versions
    import sys
    info = {'python': sys.version, 'os': os.name}
    if kwargs.get('tf', None):
        tf = kwargs['tf']
        info['tf_is_built_with_cuda'] = tf.test.is_built_with_cuda()
        info['is_built_with_gpu_support'] = tf.test.is_built_with_gpu_support()
        info['tf_is_gpu_available'] = tf.test.is_gpu_available()
        info['eager_execution'] = tf.executing_eagerly()

    for k,v in kwargs.items():
        if v is not None:
            info[k] = getattr(v, '__version__', 'NotDefined')

    return info
