package com.jihoonkim.water

import android.content.Context

/** App settings, stored on the phone. Defaults come from secrets.properties at build time. */
class Settings(context: Context) {
    private val p = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var server: String
        get() = p.getString("server", null) ?: BuildConfig.DEFAULT_SERVER
        set(v) = p.edit().putString("server", v.trim().trimEnd('/')).apply()

    var clientId: String
        get() = p.getString("clientId", null) ?: BuildConfig.DEFAULT_CLIENT_ID
        set(v) = p.edit().putString("clientId", v.trim()).apply()

    var clientSecret: String
        get() = p.getString("clientSecret", null) ?: BuildConfig.DEFAULT_CLIENT_SECRET
        set(v) = p.edit().putString("clientSecret", v.trim()).apply()

    var alertsEnabled: Boolean
        get() = p.getBoolean("alertsEnabled", false)
        set(v) = p.edit().putBoolean("alertsEnabled", v).apply()

    /** Notify when the last hour's average TDS goes above this (ppm). */
    var tdsLimit: Float
        get() = p.getFloat("tdsLimit", 30f)
        set(v) = p.edit().putFloat("tdsLimit", v).apply()

    /** Notify when no reading has arrived for this many minutes. */
    var staleMinutes: Int
        get() = p.getInt("staleMinutes", 60)
        set(v) = p.edit().putInt("staleMinutes", v).apply()

    // Remember which alerts were already sent, so each problem notifies once
    var tdsAlerted: Boolean
        get() = p.getBoolean("tdsAlerted", false)
        set(v) = p.edit().putBoolean("tdsAlerted", v).apply()

    var staleAlerted: Boolean
        get() = p.getBoolean("staleAlerted", false)
        set(v) = p.edit().putBoolean("staleAlerted", v).apply()
}
