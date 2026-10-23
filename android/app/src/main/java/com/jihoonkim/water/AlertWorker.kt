package com.jihoonkim.water

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.time.Duration
import java.time.Instant
import java.util.concurrent.TimeUnit

/**
 * Runs about every 15 minutes (Android's minimum for background checks) and
 * notifies when filtered-water TDS is high or the sensor has gone quiet.
 * Each problem notifies once, and again only after it has cleared.
 */
class AlertWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val s = Settings(applicationContext)
        if (!s.alertsEnabled) return Result.success()
        val api = Api(s)

        val latest = try {
            api.latest()
        } catch (e: ApiException) {
            return Result.success()  // phone offline or server down: try again next time
        }

        // Sensor stopped reporting
        val ageMin = Duration.between(latest.time, Instant.now()).toMinutes()
        if (ageMin >= s.staleMinutes) {
            if (!s.staleAlerted) {
                notify(STALE_ID, "Sensor stopped reporting",
                    "No reading for ${formatAge(ageMin)}. Check the sensor's power and WiFi.")
                s.staleAlerted = true
            }
        } else {
            s.staleAlerted = false
        }

        // High TDS: use the last hour's average so a single noisy reading doesn't alert
        val avg = try {
            api.series(hours = 1, points = 12).mapNotNull { it.tdsPpm }.average()
        } catch (e: ApiException) {
            Double.NaN
        }
        if (!avg.isNaN()) {
            if (avg > s.tdsLimit) {
                if (!s.tdsAlerted) {
                    notify(TDS_ID, "TDS is high: ${"%.0f".format(avg)} ppm",
                        "Above your limit of ${"%.0f".format(s.tdsLimit)} ppm. The filter may need changing.")
                    s.tdsAlerted = true
                }
            } else if (avg < s.tdsLimit * 0.9) {
                s.tdsAlerted = false  // a little below the limit before re-arming
            }
        }
        return Result.success()
    }

    private fun notify(id: Int, title: String, text: String) {
        val ctx = applicationContext
        if (!NotificationManagerCompat.from(ctx).areNotificationsEnabled()) return
        ensureChannel(ctx)
        val open = PendingIntent.getActivity(
            ctx, 0, Intent(ctx, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_drop)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        try {
            NotificationManagerCompat.from(ctx).notify(id, n)
        } catch (e: SecurityException) {
            // notification permission was revoked
        }
    }

    companion object {
        private const val CHANNEL = "alerts"
        private const val WORK = "water-alerts"
        private const val TDS_ID = 1
        private const val STALE_ID = 2

        fun ensureChannel(ctx: Context) {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Water alerts", NotificationManager.IMPORTANCE_DEFAULT)
                    .apply { description = "High TDS and sensor offline alerts" }
            )
        }

        /** Start or stop the background checks to match the setting. */
        fun schedule(ctx: Context, enabled: Boolean) {
            val wm = WorkManager.getInstance(ctx)
            if (!enabled) {
                wm.cancelUniqueWork(WORK)
                return
            }
            val req = PeriodicWorkRequestBuilder<AlertWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            wm.enqueueUniquePeriodicWork(WORK, ExistingPeriodicWorkPolicy.UPDATE, req)
        }

        fun formatAge(minutes: Long): String = when {
            minutes < 60 -> "$minutes min"
            minutes < 48 * 60 -> "${minutes / 60} h"
            else -> "${minutes / (24 * 60)} days"
        }
    }
}
