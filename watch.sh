#!/bin/bash

mkdir -p site

ls *.dot | entr sh -c 'create.sh'