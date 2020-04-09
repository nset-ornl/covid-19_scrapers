#!/usr/bin/env bash
# usage {{{1 ------------------------------------------------------------------
#/ Usage: 
#/        ./dev.sh [OPTIONS]
#/    
#/   -h|-?|--help)
#/       show this help and exit
#/
#/   -r|--run)
#/       spin up the containers
#/
#/   -L|--log-container)
#/       specify which container to log (defaults to scraper)
#/
#/   -b|--build-base)
#/       build the base image
#/
#/   -p|--push)
#/       push the base image
#/
#/   -t|--tag
#/       the tag for the image without the label
#/
#/   -l|--label)
#/       specify label for image
#/
#/   -u|--up)
#/       spin up the docker stack
#/
#/   -P|--pull)
#/       get the latest base image
#/
#/   -d|--deploy)
#/       deploy the stack for PRODUCTION
#/
#/   -i|--interactive)
#/       enter specified container interactively
#/
#/   --no-cache)
#/       build without cache; WARNING this may take > 1 hr depending on specs
#/
# 1}}} ------------------------------------------------------------------------
# environment {{{1 ------------------------------------------------------------
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
BASE="$( basename "$DIR")"
TAG="code.ornl.gov:4567/nset_covid19/covid19scrapers/base"
LABEL="latest"
BUILD=0
PUSH=0
UP=0
INTERACTIVE=0
DE=0
RETRIEVE=0
CACHE=1
RUN=0
LOG_CONTAINER="scraper"
DEPLOY=0
# 1}}} ------------------------------------------------------------------------
# functions {{{1 --------------------------------------------------------------
banner() { # {{{2 -------------------------------------------------------------
  echo -e "\\e[35m"
  cat << EOF
                _     _ _
  ___ _____   _(_) __| | |__  
 / __/ _ \\ \\ / / |\/ _\` | '_ \ 
| (_| (_) \\ V /| | (_| | |_) |
 \\___\\___/ \\_/ |_|\\__,_|_.__/    devtools

EOF
  echo -e "\\e[39m"
                              
} # 2}}} ----------------------------------------------------------------------
die() { # {{{2 ----------------------------------------------------------------
  echo -e "\\e[31mFAILURE:\\e[39m $1"
  exit 1
} # 2}}} ----------------------------------------------------------------------
info() { # {{{2
  echo -e "\\e[36mINFO:\\e[39m $1"
} # 2}}}
warn() { # {{{2 ---------------------------------------------------------------
  echo -e "\\e[33mWARNING:\\e[39m $1"
} # 2}}} ----------------------------------------------------------------------
show_help() { # {{{2 ----------------------------------------------------------
  grep '^#/' "${BASH_SOURCE[0]}" | cut -c4- || \
    die "Failed to display usage information"
} # 2}}} ----------------------------------------------------------------------
# 1}}} ------------------------------------------------------------------------
# arguments {{{1 --------------------------------------------------------------
while :; do
  case $1 in # check arguments {{{2 -------------------------------------------
    -b|--build-base) # {{{3
      BUILD=1
      shift
      ;; # 3}}}
    -p|--push) # {{{3
      PUSH=1
      shift
      ;; # 3}}}
    -i|--interactive) # {{{3
      UP=1
      INTERACTIVE=1
      DE="$2"
      shift
      ;; # 3}}}
    -t|--tag) # {{{3
      TAG=$2
      shift 2
      ;; # 3}}}
    -l|--label) # {{{3
      LABEL=$2
      shift 2
      ;; # 3}}}
    -L|--log-container) # {{{3
      LOG_CONTAINER=$2
      shift 2
      ;; # 3}}}
    -u|--up) # {{{3
      UP=1
      shift
      ;; # 3}}}
    -P|--pull) # {{{3
      RETRIEVE=1
      shift
      ;; # 3}}}
    -r|--run) # {{{3
      RUN=1
      shift
      ;; # 3}}}
    --no-cache) # {{{3
      CACHE=0
      shift
      ;; # 3}}}
    -d|--deploy) # {{{3
      DEPLOY=1
      shift
    ;; # 3}}}
    -h|-\?|--help) # help {{{3 ------------------------------------------------
      banner
      show_help
      exit
      ;; # 3}}} ---------------------------------------------------------------
    -?*) # unknown argument {{{3 ----------------------------------------------
      warn "Unknown option (ignored): $1"
      shift
      ;; # 3}}} ---------------------------------------------------------------
    *) # default {{{3 ---------------------------------------------------------
      break # 3}}} ------------------------------------------------------------
  esac # 2}}} -----------------------------------------------------------------
done
# 1}}} ------------------------------------------------------------------------
# logic {{{1 ------------------------------------------------------------------
banner
IMAGE_TAG="$TAG:$LABEL"
if [ "$RETRIEVE" -eq "1" ]; then
  info "Pulling latest image $IMAGE_TAG"
  docker pull "$IMAGE_TAG"
fi
if [ "$BUILD" -eq "1" ]; then
  info "Building image $IMAGE_TAG"
  if [ "$CACHE" -eq "1" ]; then
    docker build -t "$IMAGE_TAG" -f base/Dockerfile base/
  elif [ "$CACHE" -eq "0" ]; then
    docker build --no-cache -t "$IMAGE_TAG" -f base/Dockerfile base/
  fi
fi
if [ "$PUSH" -eq "1" ]; then
  info "Pushing image $IMAGE_TAG"
  docker push "$IMAGE_TAG"
fi
if [ "$UP" -eq "1" ]; then
  info "Spinning up stack"
  docker-compose up -d --build scraper tidy db api
fi
if [ "$INTERACTIVE" -eq "1" ]; then
  info "Dropping into shell of $DE"
  docker exec -it "${BASE}_${DE}_1" bash
fi
if [[ "$RUN" -eq "1" && "$DEPLOY" -eq "1" ]]; then
  die "Cannot specify both RUN and DEPLOY flags"
fi
if [ "$RUN" -eq "1" ]; then
  info "Running"
  docker-compose down && docker-compose up -d --build api db tidy scraper && \
    docker logs -f "$LOG_CONTAINER"
fi
if [ "$DEPLOY" -eq "1" ]; then
  info "Deploy bypassing overrides file"
  docker-compose -f docker-compose.yml down && \
    docker-compose -f docker-compose.yml up -d --build api db tidy scraper
fi
# 1}}} ------------------------------------------------------------------------
