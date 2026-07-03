"""
Aegis — отрисовка графиков.
Jupyter: inline matplotlib с тёмной темой Aegis.
Terminal: ASCII-sparkline + текстовая таблица.
"""
import sys
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..metrics.collector import MetricCollector


AEGIS_COLORS = [
    '#e8192c',
    '#4a9eff',
    '#3ecf8e',
    '#a855f7',
    '#f59e0b',
    '#ec4899',
    '#34d399',
    '#60a5fa',
]

AEGIS_DARK_BG = '#0a0a0a'
AEGIS_PANEL_BG = '#111111'
AEGIS_TEXT = '#e0e0e0'
AEGIS_GRID = '#1e1e1e'
AEGIS_BORDER = '#2a2a2a'


def _apply_aegis_theme(ax, title: str, color: str):
    ax.set_facecolor(AEGIS_PANEL_BG)
    ax.set_title(title, color=color, fontsize=10, fontweight='bold', pad=8)
    ax.set_xlabel('Шаг', color='#555555', fontsize=8)
    ax.tick_params(colors='#444444', labelsize=7)
    ax.grid(True, color=AEGIS_GRID, linewidth=0.5, linestyle='--')
    for spine in ax.spines.values():
        spine.set_edgecolor(AEGIS_BORDER)


class JupyterRenderer:
    def __init__(self, smoothing: bool = True, max_cols: int = 3):
        self._smoothing = smoothing
        self._max_cols = max_cols
        self._fig = None

    def render(self, collector: "MetricCollector", run_name: str = ""):
        try:
            import matplotlib.pyplot as plt
            from IPython.display import display, clear_output
        except ImportError:
            self._render_text_fallback(collector, run_name)
            return

        series_map = collector.all_series()
        user_metrics = {k: v for k, v in series_map.items() if not k.startswith('sys/')}

        if not user_metrics:
            return

        n = len(user_metrics)
        cols = min(self._max_cols, n)
        rows = (n + cols - 1) // cols

        fig = plt.Figure(
            figsize=(5.5 * cols, 3.5 * rows),
            facecolor=AEGIS_DARK_BG,
        )

        title = f"Aegis — {run_name} | Шаг {collector.step}"
        fig.suptitle(title, color='#e8192c', fontsize=11, fontweight='bold', y=1.01)

        axes = [fig.add_subplot(rows, cols, i + 1) for i in range(n)]

        for idx, (metric_name, series) in enumerate(user_metrics.items()):
            ax = axes[idx]
            color = AEGIS_COLORS[idx % len(AEGIS_COLORS)]
            steps = series.steps
            values = series.smoothed if self._smoothing else series.values
            raw = series.values

            if self._smoothing and len(raw) > 1:
                ax.plot(steps, raw, color=color, alpha=0.2, linewidth=0.8)

            if len(steps) > 1:
                ax.plot(steps, values, color=color, linewidth=2.0, solid_capstyle='round')
            elif steps:
                ax.scatter(steps, values, color=color, s=20, zorder=5)

            if series.last is not None:
                ax.annotate(
                    f" {series.last:.4f}",
                    xy=(steps[-1], values[-1]),
                    xytext=(5, 0),
                    textcoords='offset points',
                    color=color,
                    fontsize=7,
                    va='center',
                )

            _apply_aegis_theme(ax, metric_name, color)

        for i in range(n, rows * cols):
            if i < len(axes):
                axes[i].set_visible(False)

        fig.tight_layout()
        clear_output(wait=True)
        display(fig)
        plt.close(fig)

    def _render_text_fallback(self, collector: "MetricCollector", run_name: str = "") -> None:
        """Текстовая HTML-таблица когда matplotlib недоступен (Notebook без matplotlib)."""
        try:
            import html as _html
            from IPython.display import display, clear_output, HTML
            series = {k: v for k, v in collector.all_series().items() if not k.startswith('sys/')}
            if not series:
                return
            rows = "".join(
                f"<tr><td><b>{_html.escape(name)}</b></td>"
                f"<td align='right'>{f'{s.last:.4f}' if s.last is not None else '&mdash;'}</td>"
                f"<td align='right'>{f'{s.best:.4f}' if s.best is not None else '&mdash;'}</td></tr>"
                for name, s in series.items()
            )
            content = (
                f"<p style='font-weight:bold;color:#e8192c'>"
                f"Aegis &mdash; {_html.escape(run_name)} | step {collector.step}</p>"
                f"<table border='1' style='border-collapse:collapse;font-size:13px'>"
                f"<tr><th>Metric</th><th>Last</th><th>Best</th></tr>"
                f"{rows}</table>"
            )
            clear_output(wait=True)
            display(HTML(content))
        except Exception:
            pass  # в самом плохом случае молчим


class TerminalRenderer:
    RED = '\033[91m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    DIM = '\033[2m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    CYAN = '\033[96m'

    COLORS = [RED, BLUE, GREEN, YELLOW, CYAN]

    def _supports_unicode(self) -> bool:
        encoding = getattr(sys.stdout, 'encoding', None)
        if not encoding:
            return False
        try:
            '┌─▁'.encode(encoding)
            return True
        except Exception:
            return False

    def _sparkline(self, values: List[float], width: int = 20, unicode_ok: bool = True) -> str:
        if not values:
            return '─' * width if unicode_ok else '-' * width
        if unicode_ok:
            bars = '▁▂▃▄▅▆▇█'
        else:
            bars = ' .:-=+*#%'
        mn, mx = min(values), max(values)
        rng = mx - mn or 1
        tail = values[-width:]
        return ''.join(
            bars[int((v - mn) / rng * (len(bars) - 1))] for v in tail
        )

    def render(self, collector: "MetricCollector", run_name: str = "",
               elapsed: str = "0s", connected: bool = True):
        series = {k: v for k, v in collector.all_series().items() if not k.startswith('sys/')}
        if not series:
            return

        unicode_ok = self._supports_unicode()
        if unicode_ok:
            conn_str = f"{self.GREEN}●{self.RESET}" if connected else f"{self.RED}○{self.RESET}"
            box_label = f"{self.BOLD}{self.RED}┌─ AEGIS{self.RESET}"
            line_char = '─'
        else:
            conn_str = f"{self.GREEN}o{self.RESET}" if connected else f"{self.RED}x{self.RESET}"
            box_label = f"{self.BOLD}{self.RED}[AEGIS]{self.RESET}"
            line_char = '-'

        print(f"\n{box_label} {conn_str}"
              f"  {self.DIM}run={run_name}  step={collector.step}  time={elapsed}{self.RESET}")
        print(f"{'Метрика':<18} {'Последнее':>12} {'Лучшее':>12} {'Тренд':>22}")
        print(f"{self.DIM}{line_char * 68}{self.RESET}")

        for idx, (name, s) in enumerate(series.items()):
            color = self.COLORS[idx % len(self.COLORS)]
            last = f"{s.last:.4f}" if s.last is not None else "—"
            best = f"{s.best:.4f}" if s.best is not None else "—"
            spark = self._sparkline(s.values, unicode_ok=unicode_ok)
            print(f"{color}{name:<18}{self.RESET} {last:>12} {self.DIM}{best:>12}{self.RESET}"
                  f"  {self.DIM}{spark}{self.RESET}")

        print(f"{self.DIM}{line_char * 68}{self.RESET}")

