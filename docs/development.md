# Development

## Running the tasks locally

The tasks are setup to be run with Docker Compose in `docker-compose.yml`. For example,
you can build the Docker image that runs `task_1` by typing:

    docker-compose build task_1

(You only need to run this again when you change the dependencies required by
the project.)

Then to run `task_1`, type:

    docker-compose run --rm task_1

Docker Compose is setup so that changes in the environment file `build/files/.env.dev`
and the files in `src` will be available without rebuilding the image.

The web server can be started with:

    docker-compose up -d web_server

and stopped with

    docker-compose stop web_server

## Entering a shell in the image

For debugging or adding dependencies, it is useful to enter a bash shell in
the Docker image:

    docker-compose run --rm shell

## Dependency management

This project manages its dependencies with
[pip-tools](https://github.com/jazzband/pip-tools).
Basically, you specify the top-level dependencies you need in
`requirements.in` and pip-tools will generate `requirements.txt`
which the Dockerfile uses as a list of resolved dependencies for
`pip`.

### Adding another runtime dependency

To adding a python library to your runtime dependencies, follow these steps:

1. Add the library name to `requirements.in`
2. Rebuild your task code:

    docker-compose build task_1

Now you can start using the dependency in your code.
3. You should also rebuild the development requirements so that the
development tools are aware of your libraries. For example, pylint
will warn you about bad import statements unless the development Docker image
has the libraries that the main Docker image has.
To rebuild the development image so that it has these requirements, run:

    docker-compose build pylint

`pylint` was used above but it could be any Docker Compose service that uses the
development image (e.g. mypy).

### Adding another development dependency

Development dependencies are libraries used during development and
testing but not used when the tasks are deployed. For example, `pytest`
is a development dependency because it is needed to run tests during
development, but not needed to run the actual tasks.

To add a python library to your development dependencies,

1. Add the library name to `dev-requirements.in`:
2. Rebuild the development image:

    docker-compose build pylint

`pylint` was used above but it could be any Docker Compose service that uses the
development image (e.g. mypy).

Now you can start using the development dependency.

## Running tests

This project uses the [pytest](https://docs.pytest.org/en/latest/)
framework to run tests. The test code is located in `/tests`. For
now there is only a trivial test which you can delete once you've
added your own. To run tests:

    docker-compose run --rm pytest

## View test coverage

This project uses the [pytest-cov](https://github.com/pytest-dev/pytest-cov)
framework to report test coverage. To get a report:

    docker-compose run --rm pytest-cov

## Check syntax

This project uses [pylint](https://www.pylint.org/) to check syntax. To check:

    docker-compose run --rm pylint

## Type checking

This project uses [mypy](http://mypy-lang.org/) to do type checking. To check:

    docker-compose run --rm mypy

The configuration for mypy is in `mypy.ini` in the project root.


## Check for security vulnerabilities

This project uses [safety](https://github.com/pyupio/safety) to
check libraries for security vulnerabilities, To check:

    docker-compose run --rm safety

## Development shell

To get a bash shell in the container that has development dependencies installed:

    docker-compose run --rm dev-shell

You can use this shell to run pytest, pylint, etc. with different options.

# Dockerfile linting

Use [hadolint](https://github.com/hadolint/hadolint) to ensure your Dockerfile follows
best practices:

    docker-compose run --rm hadolint

## Continuous Integration using GitHub Actions

The project uses [GitHub Actions](https://github.com/features/actions) to
perform Continuous Integration (CI). It runs pytest, pylint, and mypy.
See `.github/workflows/push.yml` to customize.
