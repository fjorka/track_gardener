import yaml
from skimage.measure._regionprops import COL_DTYPES, _require_intensity_image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import track_gardener.db.db_functions as fdb
from track_gardener.db.db_model import CellDB
from track_gardener.db.db_validate import check_database_connection
from track_gardener.signals.build_signals_function import (
    check_unique_names,
    load_function_from_path,
)


def validateConfigFile(file_path):
    """
    Test whether the config file is executable.
    """

    # load the config file
    with open(file_path) as config_file:
        try:
            config = yaml.safe_load(config_file)
        except yaml.YAMLError as exc:
            return False, f"Error loading the config file: {exc}"

    # test if the database path is correct
    if "database" not in config:
        return False, "The database path is missing in the config file."
    else:
        database_path = config["database"]["path"]
        status, msg = check_database_connection(database_path)
        if status is False:
            return False, msg

    # test whether signal channels are provided
    if "signal_channels" not in config:
        return False, "No signal channels provided in the config file."
    else:
        for ch in config["signal_channels"]:
            if "zarr" not in ch["path"]:
                return False, "Accepting only zarr files as signal channels."

    # test requested regionprops functions without signals
    req_regionprops_no_signal = [
        x["function"]
        for x in config["cell_measurements"]
        if x["source"] == "regionprops" and "channels" not in x
    ]
    if not all(x in COL_DTYPES for x in req_regionprops_no_signal):
        return (
            False,
            "Requested regionprops functions without signals are not supported.",
        )

    # test requested regionprops functions with signals
    req_regionprops_signal = [
        x["function"]
        for x in config["cell_measurements"]
        if x["source"] == "regionprops" and "channels" in x
    ]
    if not all(x in _require_intensity_image for x in req_regionprops_signal):
        return (
            False,
            "Requested regionprops functions with signals are not supported.",
        )

    # test track_gardener functions
    req_tr_gard_functions = [
        x["function"]
        for x in config["cell_measurements"]
        if x["source"] == "track_gardener"
    ]

    for f in req_tr_gard_functions:
        if not hasattr(fdb, f):
            return (
                False,
                f'Requested Track Gardener function "{f}" is not implemented. Use a custom function instead.',
            )

    # test custom functions
    req_custom_functions = [
        x
        for x in config["cell_measurements"]
        if x["source"] != "regionprops" and x["source"] != "track_gardener"
    ]
    for f in req_custom_functions:
        status, msg = load_function_from_path(f["source"], f["function"])
        if status is False:
            return False, msg

    # test unique measurements names
    status, output = check_unique_names(config)
    if status is False:
        return False, output

    # check that the requested signals are in the database
    engine = create_engine(f"sqlite:///{database_path}")
    session = sessionmaker(bind=engine)()
    example_cell = session.query(CellDB).first()
    signal_list = list(example_cell.signals.keys())
    for x in output:
        if x not in signal_list:
            return (
                False,
                f'Requested signal "{x}" not present in the database.',
            )

    # test that graphs request existing measurements
    req_graphs = [signal for x in config["graphs"] for signal in x["signals"]]
    for g in req_graphs:
        if g not in output:
            return (
                False,
                f'Requested graph for "{g}" not present in measurements.',
            )

    return True, "Config file is executable."
