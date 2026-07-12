const { subWeeks, format } = require('date-fns');
const now = new Date('2026-07-12T12:00:00Z');
for (let i = 15; i >= 0; i--) {
    const d = subWeeks(now, i);
    const weekStart = new Date(d);
    weekStart.setDate(d.getDate() - d.getDay());
    console.log(format(weekStart, 'MMM d'), format(weekStart, 'yyyy-MM-dd'));
}
