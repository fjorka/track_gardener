Track Gardener loads experimental data, measurements, and visualisation options from a YAML configuration file.
When the user selects a configuration file in the settings tab, the plugin first validates the file and then reads the parameters.

The configuration file is divided into several sections.

### experiment_settings
Defines general metadata for the session.
`experiment_name` and `experiment_description` are optional strings used only to display context inside Track Gardener.

Example:
```yaml
experiment_settings:
  experiment_name: Test experiment
  description: Test description of an experiment
```

### signal_channels
List of image channels that will be loaded into napari. Each channel dictionary may contain:

- `name` – label used inside the viewer.
- `path` – path to a zarr file containing the image data. Validation enforces the `*.zarr` format.
- `lut` – colour map displayed in napari.
- `contrast_limits` – optional two-element list setting contrast limits.

### cell_measurements

Describes which measurements should be computed for every cell. The configuration loader dynamically builds a measurement routine based on these entries.

Each entry defines:

- `function` – name of the measurement function.
- `source` – where the function is implemented:
    - `regionprops` refers to `skimage.measure.regionprops` properties.
    - `track_gardener` refers to functions provided by the plugin.
    - any other string is treated as a path to a Python file containing a custom function.
- `channels` – optional list of channel names used as intensity images.
- `name` – optional custom name for the resulting signal.
- Additional keyword arguments are forwarded to the measurement function (e.g. `ring_width` for `ring_intensity`).
