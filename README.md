# track-gardener

[![License BSD-3](https://img.shields.io/pypi/l/track-gardener.svg?color=green)](https://github.com/fjorka/track-gardener/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/track-gardener.svg?color=green)](https://pypi.org/project/track-gardener)
[![Python Version](https://img.shields.io/pypi/pyversions/track-gardener.svg?color=green)](https://python.org)
[![tests](https://github.com/fjorka/track_gardener/actions/workflows/test_and_deploy.yaml/badge.svg)](https://github.com/fjorka/track_gardener/actions/workflows/test_and_deploy.yaml)
[![codecov](https://codecov.io/github/fjorka/track_gardener/graph/badge.svg?token=436E4J8MUI)](https://codecov.io/github/fjorka/track_gardener)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/track-gardener)](https://napari-hub.org/plugins/track-gardener)
[![Docs](https://img.shields.io/badge/docs-online-blue)](https://fjorka.github.io/track_gardener/)

A plugin facilitating manual curation of tracking results.


----------------------------------

This [napari] plugin was generated with [copier] using the [napari-plugin-template].

<!--
Don't miss the full getting started guide to set up your new package:
https://github.com/napari/napari-plugin-template#getting-started

and review the napari docs for plugin developers:
https://napari.org/stable/plugins/index.html
-->
<picture>
  <source srcset="./src/track_gardener/icons/track_gardener_logo.png" media="(prefers-color-scheme: dark)">
  <source srcset="./src/track_gardener/icons/track_gardener_logo_white.png" media="(prefers-color-scheme: light)">
  <img src="./src/track_gardener/icons/track_gardener_logo_light.png" alt="Project Logo" width="300"/>
</picture>

## Installation

Preliminary installation instructions while the package is not in pypi:

- Create a conda environment:
```bash
conda create -y -n gardener-env python=3.10 -c conda-forge
```
- Activate the environment:
```bash
conda activate gardener-env
```
- Install napari (detailed instructions here: https://napari.org/dev/tutorials/fundamentals/installation.html):
```bash
pip install "napari[all]"
```
- Install the Track-Gardener plugin directly from github:
```bash
pip install git+https://github.com/fjorka/track_gardener.git
```

## Contributing

Contributions are very welcome. Tests can be run with [tox], please ensure
the coverage at least stays the same before you submit a pull request.

## License

Distributed under the terms of the [BSD-3] license,
"track-gardener" is free and open source software

## Issues

If you encounter any problems, please [file an issue] along with a detailed description.

[napari]: https://github.com/napari/napari
[copier]: https://copier.readthedocs.io/en/stable/
[@napari]: https://github.com/napari
[MIT]: http://opensource.org/licenses/MIT
[BSD-3]: http://opensource.org/licenses/BSD-3-Clause
[GNU GPL v3.0]: http://www.gnu.org/licenses/gpl-3.0.txt
[GNU LGPL v3.0]: http://www.gnu.org/licenses/lgpl-3.0.txt
[Apache Software License 2.0]: http://www.apache.org/licenses/LICENSE-2.0
[Mozilla Public License 2.0]: https://www.mozilla.org/media/MPL/2.0/index.txt
[napari-plugin-template]: https://github.com/napari/napari-plugin-template

[napari]: https://github.com/napari/napari
[tox]: https://tox.readthedocs.io/en/latest/
[pip]: https://pypi.org/project/pip/
[PyPI]: https://pypi.org/
