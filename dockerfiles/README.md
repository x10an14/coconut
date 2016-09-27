## Choose the Dockerfile.X of your choosing, and execute: ##


1. `docker build -t <your tag> -f <path to Dockerfile.X of your choosing> .` while in the root git repo folder.

2. Then execute `docker run <your tag from 1.>` =)

### EXAMPLE ###
`cd 'git repo'`
`docker build my_coconut_build_test_image:v1.0 -f dockerfiles Dockerfile.execute_tests .`
`docker run my_coconut_build_test_image:v1.0`

