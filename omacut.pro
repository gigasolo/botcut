QT += core gui qml quick quickcontrols2 multimedia dbus

CONFIG += c++17 release link_pkgconfig
PKGCONFIG += libsecret-1
TARGET = botcut
TEMPLATE = app

HEADERS += \
    src/filepicker.h \
    src/portalfilepicker.h \
    src/edit.h \
    src/ffmpeg.h \
    src/thumbworker.h \
    src/thumbprovider.h \
    src/timeline.h \
    src/backend.h \
    src/cutjob.h \
    src/keystore.h

SOURCES += \
    src/main.cpp \
    src/cutjob.cpp \
    src/portalfilepicker.cpp \
    src/edit.cpp \
    src/ffmpeg.cpp \
    src/thumbworker.cpp \
    src/thumbprovider.cpp \
    src/timeline.cpp \
    src/backend.cpp \
    src/keystore.cpp

RESOURCES += src/resources.qrc
