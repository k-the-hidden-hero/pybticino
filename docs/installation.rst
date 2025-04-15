============
Installation
============

.. note::
   This library is not yet published on PyPI. The following instructions
   are for installing from a local clone of the repository.

Prerequisites
-------------

*   Python 3.9 or higher (verify exact minimum version if known)
*   pip

Installation Steps
------------------

1.  **Clone the repository:**

    .. code-block:: bash

       git clone https://github.com/TheKomputerKing/bticinoreverse.git # Replace with actual URL if different
       cd bticinoreverse

2.  **Install the library:**

    It's recommended to install the library in a virtual environment.

    .. code-block:: bash

       # Create and activate a virtual environment (optional but recommended)
       python -m venv .venv
       source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`

       # Install the library in editable mode
       pip install -e .

    This installs the library in "editable" mode, meaning changes you make to the
    source code in the `src/` directory will be immediately reflected when you
    import and use the library.

Once published on PyPI, you will be able to install it using:

.. code-block:: bash

   pip install pybticino
