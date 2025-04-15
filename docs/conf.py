"""Configuration file for the Sphinx documentation builder for pybticino.

This file configures Sphinx to build the documentation for the pybticino
library, including settings for project information, extensions, and HTML output.
"""

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

from pathlib import Path  # Import Path
import sys

# Point to the source code directory relative to the docs directory
# Use pathlib instead
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path.resolve()))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "pybticino"
copyright = "2025, k-the-hidden-hero"  # Replace with actual year/author if different
author = "k-the-hidden-hero"  # Replace with actual author if different

# Attempt to get version from __init__.py - replace with a fixed version if needed
try:
    from pybticino import __version__ as release
except ImportError:
    release = "0.1.0"  # Fallback version

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",  # Include documentation from docstrings
    "sphinx.ext.napoleon",  # Support for Google and NumPy style docstrings
    "sphinx.ext.viewcode",  # Add links to source code
    "sphinx.ext.intersphinx",  # Link to other projects' documentation
    "myst_parser",  # Allow Markdown files
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
source_suffix = {
    ".rst": "restructuredtext",
    ".txt": "markdown",
    ".md": "markdown",
}

# The master toctree document.
master_doc = "index"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"  # Read the Docs theme

html_static_path = ["_static"]

# -- Options for autodoc -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#configuration

autodoc_member_order = "bysource"  # Order members by source code order
autodoc_default_options = {
    "members": True,
    "undoc-members": True,  # Include members without docstrings (though we added them)
    "show-inheritance": True,
}

# -- Options for intersphinx extension ---------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#configuration

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "aiohttp": ("https://docs.aiohttp.org/en/stable/", None),
    "websockets": ("https://websockets.readthedocs.io/en/stable/", None),
}

# -- Options for Napoleon extension ------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#configuration

napoleon_google_docstring = True
napoleon_numpy_docstring = False  # Set to True if you use NumPy style
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
