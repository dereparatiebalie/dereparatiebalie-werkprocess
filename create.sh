#!/bin/bash

for file in *.dot; do dot -Tsvg "$file" -o "site/${file%.dot}.svg"; done