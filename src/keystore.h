#pragma once

#include <QString>

// Where a pasted xAI key lives between launches. The app uses the login
// keyring. Tests use the memory store so they never touch the session keyring.
class KeyStore {
public:
    virtual ~KeyStore() = default;
    virtual QString load() = 0;
    virtual bool save(const QString &secret) = 0;
    virtual bool forget() = 0;
};

class MemoryKeyStore : public KeyStore {
public:
    QString load() override { return m_secret; }
    bool save(const QString &secret) override {
        m_secret = secret;
        return true;
    }
    bool forget() override {
        m_secret.clear();
        return true;
    }

private:
    QString m_secret;
};

class LibsecretKeyStore : public KeyStore {
public:
    QString load() override;
    bool save(const QString &secret) override;
    bool forget() override;
};
