#!/usr/bin/env bash
# Read-only diagnostics: version queries only, no build or benchmark submission.
printf '%s\n' 'Architecture:'
uname -m
printf '\n%s\n' 'Compiler commands visible in PATH (candidates only):'
found=0
for compiler in gcc swgcc swcc sw5cc sw9cc sw9gcc mpicc; do
  if location=$(command -v "$compiler" 2>/dev/null); then
    printf '%s: %s\n' "$compiler" "$location"
    found=1
  fi
done
if [ "$found" -eq 0 ]; then
  printf '%s\n' 'No listed compiler is visible. Check the site toolchain environment.'
fi
if command -v gcc >/dev/null 2>&1; then
  printf '\n%s\n' 'gcc target:'
  gcc_target=$(gcc -dumpmachine 2>/dev/null)
  printf '%s\n' "$gcc_target"
  case "$gcc_target" in
    x86_64*|i?86*|aarch64*|arm*)
      printf '%s\n' 'This gcc targets the login/host architecture, not Sunway MPE/CPE.'
      ;;
  esac
  printf '\n%s\n' 'gcc version/configuration:'
  gcc -v 2>&1
fi
printf '\n%s\n' 'Environment modules:'
if type module >/dev/null 2>&1; then
  module list 2>&1
  printf '\n%s\n' 'Available modules (select the toolchain documented by the site):'
  module avail 2>&1
else
  printf '%s\n' 'No module command in this shell. Use the site-provided environment setup.'
fi
