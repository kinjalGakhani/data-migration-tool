# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configuration for test sessions.

This is a configuration file for use with `nox <https://nox.thea.codes/>`__.

This configuration is modelled after the one for the `google-cloud-biguery
<https://github.com/googleapis/python-bigquery/blob/master/noxfile.py>`__
package.
"""

import os

import nox

# Python version used for linting.
DEFAULT_PYTHON_VERSION = "3.8"

# Python versions used for testing.
PYTHON_VERSIONS = ["3.7", "3.8", "3.9", "3.10"]

LINT_PACKAGES = ["flake8", "black==22.3.0", "isort"]


def _setup_session_requirements(session, extra_packages=[]):
    """Install requirements for nox tests."""
    session.install("--upgrade", "pip", "pytest", "pytest-mock", "wheel")
    if extra_packages:
        session.install(*extra_packages)


@nox.session(python=DEFAULT_PYTHON_VERSION, venv_backend="venv")
def lint(session):
    """Run linters.
    Returns a failure if the linters find linting errors or sufficiently
    serious code quality issues.
    """
    _setup_session_requirements(session, extra_packages=LINT_PACKAGES)
    session.run("flake8", ".")
    session.run("isort", "--check", "--profile=black", ".")
    session.run("black", "--check", ".")


@nox.session(python=DEFAULT_PYTHON_VERSION, venv_backend="venv")
def format_all(session):
    """Run black and isort.
    Format code to uniform standard.
    """
    # Pin a specific version of black, so that the linter doesn't conflict with
    # contributors.
    _setup_session_requirements(session, extra_packages=LINT_PACKAGES)
    session.run("black", ".")
    session.run("isort", "--profile=black", ".")


@nox.session(python=DEFAULT_PYTHON_VERSION, venv_backend="venv")
def unit(session):
    _setup_session_requirements(session)
    test_paths = [
        os.path.join("src", "tests"),
        os.path.join("src", "translation", "event_listener"),
        os.path.join("src", "datamigration", "scripts", "teradata", "agent_controller"),
    ]
    session.install(
        "--upgrade",
        "-r",
        os.path.join(
            "src",
            "tests",
            "requirements-test.txt",
        ),
    )
    # Run pytest against the unit tests in all test paths assigned above.
    for test_path in test_paths:
        session.run(
            "pytest",
            "--quiet",
            test_path,
        )
