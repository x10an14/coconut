## Choose the Dockerfile.X of your choosing, and execute: ##


1. `docker build -t <your tag> -f <path to Dockerfile.X of your choosing> .` while in the root git repo folder.

2. Then execute `docker run <your tag from 1.>` =)

### EXAMPLE 1 ###
`cd 'git repo'`

`docker build -t my_coconut_build_test_image:v1.0 -f dockerfiles Dockerfile.execute_tests .`

`docker run my_coconut_build_test_image:v1.0`

### EXAMPLE 2 ###
`cd 'git repo'`

`docker build -t coconut/ipython_shell:1.0 -f dockerfiles Dockerfile.pip_ipython_shell .`

`docker run --rm -it coconut/ipython_shell:1.0`

