@file:OptIn(ExperimentalMaterial3Api::class)

package com.jihoonkim.water

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val settings = Settings(this)
        AlertWorker.schedule(this, settings.alertsEnabled)
        setContent { WaterTheme { App(settings) } }
    }
}

// ------------------------------------------------------------------ theme --

@Composable
fun WaterTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val ctx = LocalContext.current
    val scheme = when {
        Build.VERSION.SDK_INT >= 31 -> if (dark) dynamicDarkColorScheme(ctx) else dynamicLightColorScheme(ctx)
        dark -> darkColorScheme(primary = Color(0xFF4FB0E8))
        else -> lightColorScheme(primary = Color(0xFF1F7FB8))
    }
    MaterialTheme(colorScheme = scheme, content = content)
}

private val Good = Color(0xFF1D9A5B)
private val Warn = Color(0xFFC9821A)
private val Bad = Color(0xFFC8463B)

enum class Tab(val label: String, val icon: Int) {
    NOW("Now", R.drawable.ic_drop),
    USAGE("Usage", R.drawable.ic_bars),
    SETTINGS("Settings", R.drawable.ic_sliders),
}

@Composable
fun App(settings: Settings) {
    var tab by rememberSaveable { mutableStateOf(Tab.NOW) }
    Scaffold(
        bottomBar = {
            NavigationBar {
                Tab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = tab == t,
                        onClick = { tab = t },
                        icon = { Icon(painterResource(t.icon), contentDescription = null) },
                        label = { Text(t.label) },
                    )
                }
            }
        },
    ) { pad ->
        Box(Modifier.padding(pad).fillMaxSize()) {
            when (tab) {
                Tab.NOW -> NowScreen(settings)
                Tab.USAGE -> UsageScreen(settings)
                Tab.SETTINGS -> SettingsScreen(settings)
            }
        }
    }
}

// ------------------------------------------------------------ shared bits --

/** Runs [block] every [periodMs] while the app is on screen, restarting when [key] changes. */
@Composable
private fun Polling(key: Any, periodMs: Long, block: suspend () -> Unit) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(key) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                block()
                delay(periodMs)
            }
        }
    }
}

@Composable
private fun rememberNow(): Instant {
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) {
        while (true) { now = Instant.now(); delay(1000) }
    }
    return now
}

@Composable
private fun Segmented(options: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    SingleChoiceSegmentedButtonRow {
        options.forEachIndexed { i, label ->
            SegmentedButton(
                selected = i == selected,
                onClick = { onSelect(i) },
                shape = SegmentedButtonDefaults.itemShape(index = i, count = options.size),
            ) { Text(label) }
        }
    }
}

@Composable
private fun Screen(content: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) { content() }
}

@Composable
private fun ErrorCard(message: String) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
        Text(
            message,
            Modifier.padding(16.dp),
            color = MaterialTheme.colorScheme.onErrorContainer,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun Tile(label: String, value: String?, unit: String, modifier: Modifier = Modifier, big: Boolean = false,
                 note: String? = null, loaded: Boolean = true) {
    Card(modifier) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(label.uppercase(), style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (value == null) {
                // No data yet shows a dash; a loaded reading without this value means the sensor isn't wired
                Text(if (loaded) "not connected" else "–", style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(
                        value,
                        style = if (big) MaterialTheme.typography.displayMedium else MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = if (big) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                    )
                    Spacer(Modifier.size(4.dp))
                    Text(unit, Modifier.padding(bottom = if (big) 8.dp else 4.dp),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            if (note != null) Text(note, style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun fmt(v: Double?, digits: Int) = v?.let { "%.${digits}f".format(it) }

private fun tdsNote(ppm: Double?) = when {
    ppm == null -> null
    ppm < 50 -> "Very low: typical of filtered water"
    ppm < 300 -> "Typical tap water"
    ppm < 600 -> "High"
    else -> "Very high"
}

// -------------------------------------------------------------------- now --

enum class Metric(val label: String, val unit: String, val digits: Int, val floorAtZero: Boolean,
                  val pick: (Reading) -> Double?) {
    TDS("TDS", "ppm", 1, true, { it.tdsPpm }),
    TEMP("Temp", "°C", 1, false, { it.tempC }),
    FLOW("Flow", "L/min", 2, true, { it.flowLpm }),
}

private val RANGES = listOf(1 to "1 h", 24 to "24 h", 168 to "7 d")

@Composable
fun NowScreen(settings: Settings) {
    val api = remember { Api(settings) }
    var latest by remember { mutableStateOf<Reading?>(null) }
    var series by remember { mutableStateOf<List<Reading>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var metric by rememberSaveable { mutableStateOf(Metric.TDS) }
    var rangeIdx by rememberSaveable { mutableIntStateOf(1) }
    val hours = RANGES[rangeIdx].first
    val now = rememberNow()

    Polling(key = hours, periodMs = 15_000) {
        try {
            latest = api.latest()
            series = api.series(hours)
            error = null
        } catch (e: ApiException) {
            error = e.message
        }
    }

    Screen {
        // Status line
        val age = latest?.let { Duration.between(it.time, now).seconds }
        Row(verticalAlignment = Alignment.CenterVertically) {
            val (color, text) = when {
                error != null -> Bad to "Can't load data"
                age == null -> MaterialTheme.colorScheme.outline to "Loading…"
                age < 120 -> Good to "Live · updated ${age}s ago"
                else -> Warn to "No new data for ${AlertWorker.formatAge(age / 60)}"
            }
            Box(Modifier.size(10.dp).background(color, CircleShape))
            Spacer(Modifier.size(8.dp))
            Text(text, style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        error?.let { ErrorCard(it) }

        val r = latest
        val loaded = r != null
        Tile("TDS", fmt(r?.tdsPpm, 1), "ppm", Modifier.fillMaxWidth(), big = true, note = tdsNote(r?.tdsPpm), loaded = loaded)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Tile("Temperature", fmt(r?.tempC, 1), "°C", Modifier.weight(1f), loaded = loaded)
            Tile("Flow", fmt(r?.flowLpm, 2), "L/min", Modifier.weight(1f), loaded = loaded)
        }

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Segmented(Metric.entries.map { it.label }, metric.ordinal) { metric = Metric.entries[it] }
                Segmented(RANGES.map { it.second }, rangeIdx) { rangeIdx = it }
                val pts = series.mapNotNull { s -> metric.pick(s)?.let { s.time to it } }
                if (pts.size < 2) {
                    Text(
                        if (metric == Metric.TEMP && pts.isEmpty()) "No temperature data yet."
                        else "Not enough data for this range yet.",
                        Modifier.padding(vertical = 40.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    LineChart(
                        pts, start = now.minus(Duration.ofHours(hours.toLong())), end = now,
                        digits = metric.digits, floorAtZero = metric.floorAtZero,
                        modifier = Modifier.fillMaxWidth().height(220.dp),
                    )
                }
            }
        }
    }
}

// ------------------------------------------------------------------ usage --

@Composable
fun UsageScreen(settings: Settings) {
    val api = remember { Api(settings) }
    var days by remember { mutableStateOf<List<DayUsage>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var spanIdx by rememberSaveable { mutableIntStateOf(0) }
    val span = listOf(7, 30)[spanIdx]

    Polling(key = span, periodMs = 60_000) {
        try {
            days = api.dailyUsage(span)
            error = null
        } catch (e: ApiException) {
            error = e.message
        }
    }

    Screen {
        Segmented(listOf("7 days", "30 days"), spanIdx) { spanIdx = it }
        error?.let { ErrorCard(it) }
        val total = days.sumOf { it.liters }
        val has = days.isNotEmpty()
        Tile("Today", if (has) fmt(days.last().liters, 1) else null, "L", Modifier.fillMaxWidth(), big = true, loaded = has)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Tile("Total, $span days", if (has) fmt(total, 0) else null, "L", Modifier.weight(1f), loaded = has)
            Tile("Daily average", if (has) fmt(total / days.size, 1) else null, "L", Modifier.weight(1f), loaded = has)
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Liters per day", style = MaterialTheme.typography.titleSmall)
                UsageBars(days, Modifier.fillMaxWidth().height(220.dp))
            }
        }
    }
}

// --------------------------------------------------------------- settings --

@Composable
fun SettingsScreen(settings: Settings) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var server by remember { mutableStateOf(settings.server) }
    var clientId by remember { mutableStateOf(settings.clientId) }
    var clientSecret by remember { mutableStateOf(settings.clientSecret) }
    var showSecret by remember { mutableStateOf(false) }
    var alerts by remember { mutableStateOf(settings.alertsEnabled) }
    var limit by remember { mutableStateOf("%.0f".format(settings.tdsLimit)) }
    var stale by remember { mutableStateOf(settings.staleMinutes.toString()) }
    var message by remember { mutableStateOf<String?>(null) }

    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        alerts = granted
        settings.alertsEnabled = granted
        AlertWorker.schedule(ctx, granted)
        message = if (granted) "Alerts on." else "Notifications are blocked, so alerts stay off."
    }

    fun save() {
        settings.server = server
        settings.clientId = clientId
        settings.clientSecret = clientSecret
        limit.toFloatOrNull()?.let { settings.tdsLimit = it }
        stale.toIntOrNull()?.let { settings.staleMinutes = it.coerceAtLeast(15) }
        message = "Saved."
    }

    Screen {
        Text("Connection", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(server, { server = it }, Modifier.fillMaxWidth(),
            label = { Text("Server address") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
        OutlinedTextField(clientId, { clientId = it }, Modifier.fillMaxWidth(),
            label = { Text("Cloudflare service token: Client ID") }, singleLine = true)
        OutlinedTextField(clientSecret, { clientSecret = it }, Modifier.fillMaxWidth(),
            label = { Text("Cloudflare service token: Client Secret") }, singleLine = true,
            visualTransformation = if (showSecret) VisualTransformation.None else PasswordVisualTransformation(),
            trailingIcon = { TextButton({ showSecret = !showSecret }) { Text(if (showSecret) "Hide" else "Show") } })
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button({ save() }) { Text("Save") }
            OutlinedButton({
                save()
                message = "Testing…"
                scope.launch {
                    message = try {
                        val r = Api(settings).latest()
                        val age = Duration.between(r.time, Instant.now()).toMinutes()
                        "Connected. Latest reading ${AlertWorker.formatAge(age)} ago."
                    } catch (e: ApiException) {
                        e.message
                    }
                }
            }) { Text("Test connection") }
        }
        message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }

        HorizontalDivider(Modifier.padding(vertical = 8.dp))

        Text("Alerts", style = MaterialTheme.typography.titleMedium)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Notify me", style = MaterialTheme.typography.bodyLarge)
                Text("When TDS is high or the sensor stops reporting. Checked about every 15 minutes.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Switch(alerts, { on ->
                if (on && Build.VERSION.SDK_INT >= 33 &&
                    ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED
                ) {
                    askPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else {
                    alerts = on
                    settings.alertsEnabled = on
                    AlertWorker.schedule(ctx, on)
                }
            })
        }
        OutlinedTextField(limit, { limit = it }, Modifier.fillMaxWidth(),
            label = { Text("Alert when TDS is above (ppm)") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            supportingText = { Text("Averaged over the last hour. Filtered water is usually under 20 ppm.") })
        OutlinedTextField(stale, { stale = it }, Modifier.fillMaxWidth(),
            label = { Text("Alert when no data for (minutes)") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        Button({ save() }) { Text("Save") }

        Text("Version ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
