# Instructions for use of Dockerized Coconut #

## Confirmed to work on: ##

```
 Version:      1.12.1
 API version:  1.24
 Go version:   go1.6.3
 Git commit:   23cf638
 Built:        Thu Aug 18 05:33:38 2016
 OS/Arch:      linux/amd64

Server:
 Version:      1.12.1
 API version:  1.24
 Go version:   go1.6.3
 Git commit:   23cf638
 Built:        Thu Aug 18 05:33:38 2016
 OS/Arch:      linux/amd64

```

## Benefits of using dockerized images ##

1. You don't have to install the required tools on your own developer machine to develop/test Coconut anymore!

2. Requirements to execute/develop Coconut are now versionalized in a format where it's easy & simple to attempt different configurations/versions!
(Like say a different version of a pip package without having to mess around with installing/uninstalling it/them on your own machine, or testing Coconut under a hypothetical version of Python 4 in the future).

## Choose the Dockerfile.X of your choosing, and execute: ##

1. `docker build -t <your tag> -f <path to Dockerfile.X of your choosing> .` while in the root git repo folder.

2. Then execute `docker run <your tag from 1.>`\*
\* If the docker image you're building is meant for an interactive process (like opening a shell), the `docker run` command needs to read `docker run -it <your docker image tag>` to work as expected.

### EXAMPLE 1 ###
1. `cd <coconut git repo>`

2. `docker build -t my_coconut_build_test_image:v1.0 -f dockerfiles/Dockerfile.execute_tests .`

3. `docker run my_coconut_build_test_image:v1.0`

### EXAMPLE 2 ###

1. `docker build -t <path to coconut git repo>/coconut/ipython_shell:1.0 -f <path to coconut git repo>dockerfiles/Dockerfile.pip_ipython_shell .`

2. `docker run --rm -it coconut/ipython_shell:1.0`\*\*

\*\* The `--rm` flag tells docker to delete the container when it's done executing.
If it is not supplied, the docker engine will save the metadata and logs of the container, and you'll have to manually delete it yourself later.
(You normally don't want to keep old and 'dead' docker container lying around indefinitely).

