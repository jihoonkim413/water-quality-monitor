package com.jihoonkim.water

import androidx.compose.foundation.Canvas
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle as DateTextStyle
import java.util.Locale

/** Line chart of (time, value) points between [start] and [end], with a soft area fill. */
@Composable
fun LineChart(
    points: List<Pair<Instant, Double>>,
    start: Instant,
    end: Instant,
    digits: Int,
    floorAtZero: Boolean,
    modifier: Modifier = Modifier,
) {
    val line = MaterialTheme.colorScheme.primary
    val grid = MaterialTheme.colorScheme.outlineVariant
    val label = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
    val measurer = rememberTextMeasurer()
    val spanHours = (end.epochSecond - start.epochSecond) / 3600.0
    val timeFmt = DateTimeFormatter.ofPattern(if (spanHours > 24) "EEE ha" else "h:mm a")
        .withZone(ZoneId.systemDefault())

    Canvas(modifier) {
        if (points.size < 2) return@Canvas
        val left = 44.dp.toPx()
        val right = 8.dp.toPx()
        val top = 8.dp.toPx()
        val bottom = 22.dp.toPx()

        var lo = points.minOf { it.second }
        var hi = points.maxOf { it.second }
        if (hi - lo < 1e-9) { lo -= 1; hi += 1 }
        val pad = (hi - lo) * 0.12
        lo -= pad; hi += pad
        if (floorAtZero && lo < 0) lo = 0.0

        val t0 = start.toEpochMilli().toDouble()
        val t1 = end.toEpochMilli().toDouble()
        fun x(t: Instant) = (left + (t.toEpochMilli() - t0) / (t1 - t0) * (size.width - left - right)).toFloat()
        fun y(v: Double) = (top + (hi - v) / (hi - lo) * (size.height - top - bottom)).toFloat()

        for (i in 0..4) {
            val v = lo + (hi - lo) * i / 4
            val yy = y(v)
            drawLine(grid, Offset(left, yy), Offset(size.width - right, yy), 1.dp.toPx())
            val t = measurer.measure("%.${digits}f".format(v), label)
            drawText(t, topLeft = Offset(left - t.size.width - 6.dp.toPx(), yy - t.size.height / 2f))
        }
        for (i in 0..2) {
            val t = Instant.ofEpochMilli((t0 + (t1 - t0) * i / 2).toLong())
            val layout = measurer.measure(timeFmt.format(t), label)
            val px = when (i) {
                0 -> left
                1 -> x(t) - layout.size.width / 2f
                else -> size.width - right - layout.size.width
            }
            drawText(layout, topLeft = Offset(px, size.height - layout.size.height.toFloat()))
        }

        val path = Path()
        points.forEachIndexed { i, (t, v) ->
            if (i == 0) path.moveTo(x(t), y(v)) else path.lineTo(x(t), y(v))
        }
        val floorY = size.height - bottom
        val area = Path().apply {
            addPath(path)
            lineTo(x(points.last().first), floorY)
            lineTo(x(points.first().first), floorY)
            close()
        }
        drawPath(area, line.copy(alpha = 0.15f))
        drawPath(path, line, style = Stroke(width = 2.dp.toPx(), join = StrokeJoin.Round))
        val (lt, lv) = points.last()
        drawCircle(line, 4.dp.toPx(), Offset(x(lt), y(lv)))
    }
}

/** Bar chart of liters per day, today's bar highlighted. */
@Composable
fun UsageBars(days: List<DayUsage>, modifier: Modifier = Modifier) {
    val bar = MaterialTheme.colorScheme.primary
    val dim = MaterialTheme.colorScheme.primary.copy(alpha = 0.45f)
    val grid = MaterialTheme.colorScheme.outlineVariant
    val label: TextStyle =
        MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
    val measurer = rememberTextMeasurer()
    val today = LocalDate.now()

    Canvas(modifier) {
        if (days.isEmpty()) return@Canvas
        val left = 40.dp.toPx()
        val top = 8.dp.toPx()
        val bottom = 22.dp.toPx()
        val maxL = days.maxOf { it.liters }.let { if (it < 1.0) 1.0 else it * 1.15 }
        val h = size.height - top - bottom
        val slot = (size.width - left) / days.size
        val barW = slot * 0.7f

        for (i in 0..3) {
            val v = maxL * i / 3
            val yy = top + h - (v / maxL * h).toFloat()
            drawLine(grid, Offset(left, yy), Offset(size.width, yy), 1.dp.toPx())
            val t = measurer.measure("%.0f".format(v), label)
            drawText(t, topLeft = Offset(left - t.size.width - 6.dp.toPx(), yy - t.size.height / 2f))
        }
        days.forEachIndexed { i, d ->
            val bh = (d.liters / maxL * h).toFloat()
            val x = left + i * slot + (slot - barW) / 2
            drawRoundRect(
                if (d.day == today) bar else dim,
                topLeft = Offset(x, top + h - bh),
                size = Size(barW, bh),
                cornerRadius = CornerRadius(3.dp.toPx()),
            )
            val showLabel = days.size <= 7 || i % 5 == (days.size - 1) % 5
            if (showLabel) {
                val text = if (days.size <= 7)
                    d.day.dayOfWeek.getDisplayName(DateTextStyle.SHORT, Locale.getDefault())
                else d.day.dayOfMonth.toString()
                val t = measurer.measure(text, label)
                drawText(t, topLeft = Offset(x + barW / 2 - t.size.width / 2f, size.height - t.size.height.toFloat()))
            }
        }
    }
}
