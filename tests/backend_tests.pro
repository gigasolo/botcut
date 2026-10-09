QT += core gui quick quickcontrols2 multimedia testlib dbus
CONFIG += c++17 testcase link_pkgconfig
PKGCONFIG += libsecret-1
TARGET = backend_tests
TEMPLATE = app

INCLUDEPATH += ../src

HEADERS += \
    ../src/backend.h \
    ../src/cutjob.h \
    ../src/keystore.h \
    ../src/edit.h \
    ../src/ffmpeg.h \
    ../src/filepicker.h \
    ../src/portalfilepicker.h \
    ../src/thumbprovider.h \
    ../src/timeline.h \
    ../src/thumbworker.h

SOURCES += \
    backend_tests.cpp \
    ../src/backend.cpp \
    ../src/keystore.cpp \
    ../src/cutjob.cpp \
    ../src/edit.cpp \
    ../src/ffmpeg.cpp \
    ../src/portalfilepicker.cpp \
    ../src/thumbprovider.cpp \
    ../src/timeline.cpp \
    ../src/thumbworker.cpp
