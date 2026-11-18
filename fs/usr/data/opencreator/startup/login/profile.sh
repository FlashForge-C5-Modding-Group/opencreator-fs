# OpenCreator login: bash with the current folder in the prompt, and the
# banner. Linked as /etc/profile.d/opencreator.sh by scripts/03-login.sh
# (see config-docs/CREATOR5_LOGIN.md).

case $- in
    *i*) ;;
    *) return 0 ;;
esac

# Back on stock firmwareExe (a revert or a FlashForge update): remove the hook
if [ "$(dd if=/usr/prog/PROGRAM/software/firmwareExe bs=1 skip=1 count=3 2>/dev/null)" = ELF ]; then
    rm -f /etc/profile.d/opencreator.sh 2>/dev/null
    return 0
fi

export PS1='\[\033[1;32m\]\u@\h\[\033[0m\]:\[\033[1;34m\]\w\[\033[0m\]\$ '

if [ ! -w "$HOME" ] && mkdir -p /usr/data/home/root 2>/dev/null; then
    export HISTFILE=/usr/data/home/root/.bash_history
fi

if [ -z "$OC_BANNER_SHOWN" ] && [ -r /usr/data/opencreator/startup/login/banner.sh ]; then
    export OC_BANNER_SHOWN=1
    sh /usr/data/opencreator/startup/login/banner.sh
fi

if [ -z "$BASH_VERSION" ] && [ -t 0 ] && [ -x /opt/bin/bash ] &&
    /opt/bin/bash -c : 2>/dev/null; then
    export SHELL=/opt/bin/bash
    exec /opt/bin/bash -l
fi
