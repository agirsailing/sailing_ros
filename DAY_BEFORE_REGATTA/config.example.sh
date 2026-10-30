# Copy this file to config.local.sh beside the main scripts.
# config.local.sh is ignored by Git and is read once at startup by each command.
# Do not execute this file. Local assignments take precedence over environment values.
export AGIR_USER_HOME=/home/boat
export AGIR_USER=boat
export AGIR_REPO_DIR=/home/boat/2025_SOFTWARE/sailing_ros
export AGIR_BRANCH=main
# Optional network target checked by run.sh before starting ROS.
# export AGIR_TARGET_IP=8.8.8.8

# Optional: leave unset to reuse origin and Git authentication.
# Both values are required when explicitly replacing HTTPS credentials.
# No interactive credential prompts: if no saved credentials exist, fill both here.
# export AGIR_GIT_USER=""
# export AGIR_GIT_TOKEN=""
