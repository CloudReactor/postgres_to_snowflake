# CloudReactor ECS Quickstart

![Tests](https://github.com/CloudReactor/cloudreactor-ecs-quickstart/workflows/Tests/badge.svg?branch=master)

This project serves as blueprint to get your python code
running in [AWS ECS Fargate](https://aws.amazon.com/fargate/),
monitored and managed by
[CloudReactor](https://www.cloudreactor.io/). See a
[summary of the benefits](https://docs.cloudreactor.io/cloudreactor.html)
of these technologies.
This project is designed with best practices and smart defaults in mind, but also to be customizable.

It has these features built-in:
* Runs, tests, and deploys everything with Docker, no local python installation required
* Deploys to AWS ECS Fargate. Tasks can be scheduled, used as services, or executed only on demand.
* Sets up tasks to be monitored and managed by CloudReactor
* Uses [pip-tools](https://github.com/jazzband/pip-tools) to manage only
top-level python library dependencies
* Uses [pytest](https://docs.pytest.org/en/latest/) (testing),
[pylint](https://www.pylint.org/) (static code analysis),
[mypy](http://mypy-lang.org/) (static type checking), and
[safety](https://github.com/pyupio/safety) (security vulnerability checking)
for quality control
* Uses [GitHub Actions](https://github.com/features/actions) for Continuous Integration (CI)

Sound good? OK, let's get started!

## Prerequisites
Run the [CloudReactor AWS Setup Wizard](https://github.com/CloudReactor/cloudreactor-aws-setup-wizard).

This wizard:
* creates an ECS cluster
* creates associated VPC, subnets and security groups (or allows you to select existing VPCs, subnets and security groups to use)
* enables CloudReactor to manage deployed tasks

The wizard enables you to have a working ECS environment in minutes; without it, you would need to set up each of these pieces individually which would be tedious and error-prone.

Finally, if you want to use CloudReactor to manage tasks, [create a user and role that can be used to deploy
tasks to ECS](https://docs.cloudreactor.io/#optional-setting-up-a-new-aws-user-with-deployment-permissions).
You can also use an administrator user or power user to deploy.
See [deployer AWS permissions](docs/deployer_aws_permissions.md) for a list of the permissions required.

## Get this project's source code

You'll need to get this project's source code onto a filesystem where you can make changes.
You can either clone this project directly, or fork it first, then clone it.

If cloning directly,

    git clone https://github.com/CloudReactor/cloudreactor-ecs-quickstart.git

## Deploy the tasks to AWS and CloudReactor

These steps show how you can deploy the example project in this repo to ECS Fargate
and have its tasks managed by CloudReactor. There are two methods of doing so,
Docker Deployment and Native Deployment.

### Docker Deployment

This deployment method builds a Docker container that is used to build and
deploy your tasks.
(This is not to be confused with the Docker container that actually runs your tasks.)
The Docker container has all the dependencies (python, ansible, aws-cli etc.)
built-in, so you don't need to install anything directly on your machine.
The Docker deployment method is appropriate for when

* you don't have python installed directly on your machine; or
* you don't want add another set of dependencies to your libraries; or
* you need to deploy from a Windows machine.

You can also use this method on an EC2 instance that has an instance profile
containing a role that has permissions to create ECS tasks. When deploying, the
AWS CLI in the container will use the temporary access key associated with the
role assigned to the EC2 instance.

The steps for Docker Deployment are:

1. Ensure you have Docker running locally, and have installed
[Docker Compose](https://docs.docker.com/compose/install/).
2. Copy `deploy/docker_deploy.env.example` to `deploy/docker_deploy.env` and
and fill in your AWS access key, access key secret, and default
region. The access key and secret would be for the AWS user you plan on using to deploy with,
possibly created in the section "Select or create user and/or role for deployment".
You may also populate this file with a script you write yourself,
for example with something that uses the AWS CLI to assume a role and gets
temporary credentials. If you are running this on an EC2 instance with an instance profile
that has deployment permissions, you can leave this file blank.
3. Copy `deploy/vars/example.yml` to `deploy/vars/<environment>.yml`, where
`<environment>` is the name of the Run Environment created above (e.g.
`staging`, `production`)
4. Open the .yml file you just created, and enter your CloudReactor API key next
to "api_key"
5. Build the Docker container that will deploy the project. In a bash shell, run:

    `./docker_build_deployer.sh <environment>`

   In a Windows command prompt, run:

    `docker_build_deployer <environment>`

`<environment>` is a required argument, which is the name of the Run Environment.

This step is only necessary once, unless you add additional configuration
to `deploy/Dockerfile`.

6) To deploy, in a bash shell, run:

    `./docker_deploy.sh <environment> [task_names]`

   In a Windows command prompt, run:

    `docker_deploy <environment>  [task_names]`

In both of these commands, `<environment>` is a required argument, which is the
name of the Run Environment. `[task_names]` is an optional argument, which is a
comma-separated list of tasks to be deployed. In this project, this can be one
or more of `task_1`, `file_io`, etc, separated by commas.
If `[task_names]` is omitted, all tasks will be deployed.

To troubleshoot deployment issues, in a bash shell, run

    ./docker_deploy_shell.sh <environment>

   In a Windows command prompt, run:

    docker_deploy_shell.bat <environment>

These commands will take you to a bash shell inside the deployer Docker
container where you can re-run the deployment script with `./deploy.sh`
and inspect the files it produces in the `build/` directory.

### Native Deployment

This deployment method installs dependencies on your machine that are needed to deploy
the project. It may either be installed in the system python environment or in
a [virtual environment](https://docs.python.org/3/tutorial/venv.html).
Native deployment is appropriate for when

* you want to deploy from a Linux or Mac OS X machine (virtual machines included); and,
* you have python installed on the machine (possibly in a virtual environment); and,
* you want to use python running directly on the machine to deploy the project.

It has the advantage that you can use the AWS configuration you
already have set up on that machine for the AWS CLI.

This method most likely will not work on Windows machines, though it has
not been tested.

The steps for Native Deployment are:

1. Ensure you have Docker running locally
2. If desired, create and use a virtual environment for deployment dependencies.
The virtual environment should use python 3.8.x.
3. Run

    `pip install -r deploy/requirements.txt`

4. Configure the AWS CLI using `aws configure`.
The access key and secret would be for the AWS user you plan on using to deploy with,
possibly created in the section "Select or create user and/or role for deployment".
You can skip this step if you are deploying from an EC2 instance that you assign
an instance role that has the required permissions.
5. Copy `deploy/vars/example.yml` to `deploy/vars/<environment>.yml`, where
`<environment>` is the name of the Run Environment created above (e.g.
`staging`, `production`)
6. Modify `deploy/vars/<environment>.yml` to contain your CloudReactor API key
7. To deploy,

    `./deploy.sh <environment> [task_names]`

where `<environment>` is a required argument, which is the
name of the Run Environment. `[task_names]` is an optional argument, which is a
comma-separated list of tasks to be deployed. In this project, this can be one or more of
`task_1`, `file_io`, etc, separated by commas. If `[task_names]` is omitted, all tasks will be deployed.

## The example tasks

Successfully deploying this example project will create two ECS tasks which are
listed in `deploy/common.yml`. They have the following behavior:

* *task_1* also prints 30 numbers and exits successfully. While it does so,
it updates the successful count and the last status message that is shown in
CloudReactor, using the status updater library. It is scheduled to run daily.
* *file_io* uses [non-persistent file storage](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html) to write and read numbers
* *web_server* uses a python library dependency (Flask) to implement a web
server and shows how to link an AWS Application Load Balancer (ALB) to a service.
It requires that an ALB and target group be setup already, so it is not enabled by default.
If enabling, you should also uncomment this line in the Dockerfile to allow the
container to receive inbound requests:

    EXPOSE 7070

## Development workflow

### Running the tasks locally

The tasks are setup to be run with Docker Compose in `docker-compose.yml`. For example,
you can build the Docker image that runs the tasks by typing:

    docker-compose build

(You only need to run this again when you change the dependencies required by
the project.)

Then to run, say `task_1`, type:

    docker-compose run --rm task_1

Docker Compose is setup so that changes in the environment file `deploy/files/.env.dev`
and the files in `src` will be available without rebuilding the image.

### More development options

See the [development guide](docs/development.md) for instructions on how to debug,
add dependencies, and run tests and checks.

## Deploying your own tasks

Now that you have deployed the example tasks, you can move your existing code to this
project. You can add or modify tasks in `deploy/common.yml` to call the commands you want,
with configuration for the schedule, retry parameters, and environment variables.
Feel free to delete the tasks that you don't need, just by removing the top level keys
in `task_name_to_config`.

## Next steps

* [Additional configuration](docs/configuration.md) options can be set or overridden
* If you want to be alerted when task executions fail, setup an
[Alert Method](https://docs.cloudreactor.io/alerts.html)
* To avoid leaking secrets (passwords, API keys, etc.), see the guide on
[secret management](docs/secret_management.md)
* For more secure [networking](https://docs.cloudreactor.io/networking.html), run your tasks on private subnets
and/or tighten your security groups.
* If you're having problems, see the [troubleshooting guide](docs/troubleshooting.html)

## Contact us

Hopefully, this example project has helped you get up and running with ECS and
CloudReactor. Feel free to reach out to us at support@cloudreactor.io to setup
an account, or if you have any questions or issues!
