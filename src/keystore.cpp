#include "keystore.h"

// Qt's `signals` macro collides with a field in the gio headers.
#undef signals
#include <libsecret/secret.h>

namespace {

const SecretSchema *botcutSchema() {
    static const SecretSchema schema = {
        "com.gigasolo.BotCut.Xai",
        SECRET_SCHEMA_NONE,
        {
            {"service", SECRET_SCHEMA_ATTRIBUTE_STRING},
            {"account", SECRET_SCHEMA_ATTRIBUTE_STRING},
        },
        0,
        nullptr,
        nullptr,
        nullptr,
        nullptr,
        nullptr,
        nullptr,
        nullptr,
    };
    return &schema;
}

void clearError(GError *error) {
    if (error)
        g_error_free(error);
}

}  // namespace

QString LibsecretKeyStore::load() {
    m_lastError.clear();
    GError *error = nullptr;
    gchar *value = secret_password_lookup_sync(botcutSchema(), nullptr, &error, "service", "botcut",
                                                "account", "xai", nullptr);
    if (error) {
        m_lastError = QString::fromUtf8(error->message);
        clearError(error);
    }
    if (!value)
        return {};
    const QString key = QString::fromUtf8(value).trimmed();
    secret_password_free(value);
    return key;
}

bool LibsecretKeyStore::save(const QString &secret) {
    if (secret.isEmpty())
        return forget();
    m_lastError.clear();
    const QByteArray bytes = secret.toUtf8();
    GError *error = nullptr;
    const gboolean ok = secret_password_store_sync(botcutSchema(), SECRET_COLLECTION_DEFAULT, "BotCut xAI",
                                                    bytes.constData(), nullptr, &error, "service", "botcut",
                                                    "account", "xai", nullptr);
    const bool failed = error != nullptr;
    if (error) {
        m_lastError = QString::fromUtf8(error->message);
        clearError(error);
    }
    return ok && !failed;
}

bool LibsecretKeyStore::forget() {
    m_lastError.clear();
    GError *error = nullptr;
    const gboolean ok =
        secret_password_clear_sync(botcutSchema(), nullptr, &error, "service", "botcut", "account", "xai", nullptr);
    const bool failed = error != nullptr;
    if (error) {
        m_lastError = QString::fromUtf8(error->message);
        clearError(error);
    }
    return ok && !failed;
}
