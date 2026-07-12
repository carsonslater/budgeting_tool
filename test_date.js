const { parse, format } = require('date-fns');

const d1 = parse("Dec 28, 25", "MMM d, yy", new Date());
const d2 = parse("Jan 18, 26", "MMM d, yy", new Date());

console.log(d1);
console.log(d2);
console.log(d1.getTime() - d2.getTime());
