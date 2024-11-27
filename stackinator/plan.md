remove support for v0.20
- search for all v0.20

test on the following spack versions:
- branch develop        -> 0.24
- branch releases/v0.20 -> raise exception
- branch releases/v0.21 -> 0.21
- branch releases/v0.22 -> 0.22
- branch releases/v0.23 -> 0.23
- tag    v0.22.3        -> v0.22
- random recent commit + --develop -> v0.24

remove `develop` as an option that is passed into makefiles
