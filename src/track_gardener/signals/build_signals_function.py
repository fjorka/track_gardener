import importlib
import os

import numpy as np
from skimage.measure import regionprops


def load_function_from_module(module_name, function_name):
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def load_function_from_path(file_path, function_name):
    # Check if the file exists
    if not os.path.exists(file_path):
        return False, f"File '{file_path}' does not exist."

    # Load the module from the specified file path
    module_name = os.path.splitext(os.path.basename(file_path))[
        0
    ]  # Extract module name from file
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    try:
        # Execute the module to load it
        spec.loader.exec_module(module)
        # Get the function
        func = getattr(module, function_name)
        return True, func  # Successfully loaded function
    except (FileNotFoundError, AttributeError) as e:
        return (
            False,
            f"Function '{function_name}' could not be loaded from '{file_path}': {e}",
        )


def check_unique_names(config):
    """
    Check that the names of the measurements are unique.
    """
    req_f = list(config["cell_measurements"])
    name_list = []
    for f in req_f:

        if "channels" in f:
            for ch in f["channels"]:
                if "name" in f:
                    name = ch + "_" + f["name"]
                else:
                    name = ch + "_" + f["function"]
                name_list.append(name)

        else:
            name = f["name"] if "name" in f else f["function"]

            name_list.append(name)

    if len(name_list) == len(set(name_list)):
        return True, name_list
    else:
        return False, "Measurement names are not unique."


def create_calculate_signals_function(config):
    """
    Function to generate for signal calculation based on the requirements in the configuration file.
    input:
        config: dictionary containing all configuration information
    output:
        calculate_cell_signals: function that calculates all signals for a given cell
    """

    ch_list = [x.get("name") for x in config["signal_channels"]]

    if config.get("cell_measurements") is None:
        return None

    # regionprops with no signal
    reg_no_signal = [
        x["function"]
        for x in config["cell_measurements"]
        if x["source"] == "regionprops" and "channels" not in x
    ]

    # regionprops with signal
    reg_signal = [
        x
        for x in config["cell_measurements"]
        if x["source"] == "regionprops" and "channels" in x
    ]

    # track gardener implemented functions
    gardener_signal = [
        x
        for x in config["cell_measurements"]
        if x["source"] == "track_gardener"
    ]

    # custom functions
    custom_signal = [
        x
        for x in config["cell_measurements"]
        if x["source"] != "track_gardener" and x["source"] != "regionprops"
    ]

    if (
        len(reg_no_signal) == 0
        and len(reg_signal) == 0
        and len(gardener_signal) == 0
        and len(custom_signal) == 0
    ):
        return None

    #######################################################################################################################
    def calculate_cell_signals(cell, t, ch_data_list):
        """
        Function to calculate signals for every given cell.
        input:
            cell: cell object from regionprops
            ch_data_list: list of all channel data
        output:
            cell_dict: dictionary containing all measurements for the cell
        """

        # create an empty dictionary
        cell_dict = {}

        #######################################################################################################################
        # add all measurements directly from regionprops
        for m in reg_no_signal:
            cell_dict[m] = cell[m]

        #######################################################################################################################
        # add all measurements from regionprops with channels
        if len(reg_signal) > 0:

            signal_cube = np.zeros(
                (
                    cell.bbox[2] - cell.bbox[0],
                    cell.bbox[3] - cell.bbox[1],
                    len(ch_list),
                ),
                dtype=ch_data_list[0].dtype,
            )
            for ind, ch in enumerate(ch_data_list):
                if ch.ndim == 3:
                    cell_signal = ch[
                        t,
                        cell.bbox[0] : cell.bbox[2],
                        cell.bbox[1] : cell.bbox[3],
                    ]
                if ch.ndim == 2:
                    cell_signal = ch[
                        cell.bbox[0] : cell.bbox[2],
                        cell.bbox[1] : cell.bbox[3],
                    ]

                signal_cube[:, :, ind] = cell_signal

            result = regionprops(
                cell.image.astype(int), intensity_image=signal_cube
            )

            for m in reg_signal:
                for ch in m["channels"]:
                    cell_dict[ch + "_" + m["name"]] = result[0][m["function"]][
                        ch_list.index(ch)
                    ]

        #######################################################################################################################
        # add measurements from the track gardener
        # for simplicity we calculate for all the channels - may be revisited later
        if len(gardener_signal) > 0:
            for m in gardener_signal:
                f = load_function_from_module(
                    "track_gardener.signals.calculate_signals", m["function"]
                )
                result = f(cell, t, ch_data_list, kwargs=m)
                for ch in m["channels"]:
                    cell_dict[ch + "_" + m["name"]] = result[ch_list.index(ch)]

        #######################################################################################################################
        # add measurements from the custom functions
        if len(custom_signal) > 0:
            for m in custom_signal:
                f = load_function_from_path(m["source"], m["function"])
                result = f(cell, t, ch_data_list, kwargs=m)
                for ch in m["channels"]:
                    cell_dict[ch + "_" + m["name"]] = result[ch_list.index(ch)]

        return cell_dict

    return calculate_cell_signals
