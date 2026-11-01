# Security Policy

Cornea Shell serves a web page to a native window on a local server, and lets that page call a short list of native actions. A bug that lets something other than your own window reach that server, or lets a page do more than it was allowed to, is a security issue.

## What counts as a vulnerability

Please report privately if you can make Cornea Shell:

- answer a request without the session cookie, or accept the start-up token more than once or after it expires;
- accept a request from another website or another program on the machine, for example through a forged `Host` or `Origin`, DNS rebinding or a cross-site request;
- serve a file outside the folder it was given (path traversal, or following a link out of it);
- let a page call a native action that was switched off, including opening files, showing notifications or receiving dropped file paths without the matching option;
- open a program, script, shortcut or network path with `open_file`;
- leak the session cookie or the start-up token, to a proxied server or into a log.

A page that is itself malicious because you chose to show it (for example with `--js-api`, which trusts every page the window loads) is a documented trade-off, not a vulnerability. Anything else that is wrong or surprising is a normal bug: please open a regular issue.

## Supported versions

Only the latest released version receives security fixes.

## Reporting

Use GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**. Please do not open a public issue for these reports.

Include the Cornea Shell version (`cornea --version`), your Windows and Python versions, the command or code you ran, and the smallest page or request that reproduces the problem. `cornea doctor` prints most of this.

You can expect an acknowledgement within a few days. Fixes are released as a patch version and credited in the changelog unless you prefer otherwise.
