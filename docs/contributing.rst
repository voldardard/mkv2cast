Contributing
============

Thank you for your interest in contributing to mkv2cast!

Getting Started
---------------

1. Fork the repository on GitHub
2. Clone your fork:

   .. code-block:: bash

      git clone https://github.com/YOUR_USERNAME/mkv2cast.git
      cd mkv2cast

3. Install development dependencies:

   .. code-block:: bash

      pip install -e ".[dev,full]"

4. Create a branch for your changes:

   .. code-block:: bash

      git checkout -b feature/my-feature

Development Workflow
--------------------

**Running tests:**

.. code-block:: bash

   pytest tests/ -v

**Running tests with coverage:**

.. code-block:: bash

   pytest tests/ -v --cov=mkv2cast --cov-report=html

**Linting:**

.. code-block:: bash

   ruff check src/ tests/
   ruff format src/ tests/

**Type checking:**

.. code-block:: bash

   mypy src/mkv2cast

**Building documentation:**

.. code-block:: bash

   cd docs
   make html

Code Style
----------

- Follow PEP 8
- Use type hints
- Write docstrings (Google style)
- Maximum line length: 120 characters

Example:

.. code-block:: python

   def convert_file(
       input_path: Path,
       cfg: Optional[Config] = None,
       backend: Optional[str] = None,
   ) -> Tuple[bool, Optional[Path], str]:
       """
       Convert a single MKV file.

       Args:
           input_path: Path to input MKV file.
           cfg: Config instance (uses global CFG if not provided).
           backend: Backend to use (auto-detected if not provided).

       Returns:
           Tuple of (success, output_path, message).
       """
       ...

Pull Request Guidelines
-----------------------

1. Ensure all tests pass
2. Add tests for new functionality
3. Update documentation if needed
4. Follow the commit message format:

   .. code-block:: text

      type(scope): description

      - feat: new feature
      - fix: bug fix
      - docs: documentation
      - test: tests
      - refactor: code refactoring

5. Keep PRs focused on a single change

Reporting Issues
----------------

When reporting bugs, please include:

- mkv2cast version (``mkv2cast --version``)
- Python version
- OS and version
- ffmpeg version
- Steps to reproduce
- Expected vs actual behavior
- Relevant log output (``--debug``)

Feature Requests
----------------

For feature requests:

- Check existing issues first
- Describe the use case
- Explain why it would be useful
- Consider if it could be a plugin instead

Translation Contributions
-------------------------

To add or improve translations:

1. Edit files in ``src/mkv2cast/locales/{lang}/LC_MESSAGES/mkv2cast.po``
2. Follow gettext format
3. Test with ``--lang {lang}``

License
-------

By contributing, you agree that your contributions will be licensed under GPL-3.0.
