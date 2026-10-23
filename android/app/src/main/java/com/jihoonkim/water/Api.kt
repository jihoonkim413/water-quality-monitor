package com.jihoonkim.water

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId

data class Reading(
    val time: Instant,
    val tdsPpm: Double?,
    val tempC: Double?,
    val flowLpm: Double?,
    val liters: Double?,
)

data class DayUsage(val day: LocalDate, val liters: Double)

class ApiException(message: String) : Exception(message)

/** Talks to the water server (through Cloudflare Access when a service token is set). */
class Api(private val settings: Settings) {

    private suspend fun get(path: String): String = withContext(Dispatchers.IO) {
        val url = URL(settings.server + path)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 15_000
            instanceFollowRedirects = false  // a redirect means Cloudflare wants a login
            if (settings.clientId.isNotEmpty()) {
                setRequestProperty("CF-Access-Client-Id", settings.clientId)
                setRequestProperty("CF-Access-Client-Secret", settings.clientSecret)
            }
        }
        try {
            when (val code = conn.responseCode) {
                200 -> conn.inputStream.bufferedReader().use { it.readText() }
                301, 302, 303, 401, 403 -> throw ApiException(
                    "Cloudflare blocked the request. Check the service token in Settings."
                )
                404 -> throw ApiException("No readings yet.")
                502, 503, 504 -> throw ApiException("The server on the NAS isn't responding ($code).")
                else -> throw ApiException("Server error $code.")
            }
        } catch (e: IOException) {
            throw ApiException("Can't reach ${url.host}: ${e.message ?: "no connection"}")
        } finally {
            conn.disconnect()
        }
    }

    suspend fun latest(): Reading = parse(JSONObject(get("/api/readings/latest")))

    /** Readings averaged into ~[points] buckets over the last [hours]. */
    suspend fun series(hours: Int, points: Int = 240): List<Reading> {
        val arr = JSONArray(get("/api/series?hours=$hours&points=$points"))
        return (0 until arr.length()).map { parse(arr.getJSONObject(it)) }
    }

    /** Liters per local calendar day for the last [days] days (oldest first, today last). */
    suspend fun dailyUsage(days: Int, zone: ZoneId = ZoneId.systemDefault()): List<DayUsage> {
        // Hourly buckets line up with local hours, so they can be summed per local day.
        val hourly = series(hours = days * 24, points = days * 24)
        val totals = hourly.groupBy { it.time.atZone(zone).toLocalDate() }
            .mapValues { (_, rs) -> rs.sumOf { it.liters ?: 0.0 } }
        val today = LocalDate.now(zone)
        return (days - 1 downTo 0).map { back ->
            val d = today.minusDays(back.toLong())
            DayUsage(d, totals[d] ?: 0.0)
        }
    }

    private fun parse(o: JSONObject) = Reading(
        time = OffsetDateTime.parse(o.getString("ts")).toInstant(),
        tdsPpm = o.num("tds_ppm"),
        tempC = o.num("temp_c"),
        flowLpm = o.num("flow_lpm"),
        liters = o.num("liters"),
    )

    private fun JSONObject.num(key: String): Double? =
        if (!has(key) || isNull(key)) null else getDouble(key)
}
