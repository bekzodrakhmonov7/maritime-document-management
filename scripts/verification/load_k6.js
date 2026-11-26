// D5: request mix dashboard 40 %, document list 30 %, readiness 30 %, 1 s think time.
// docker run --rm -v <dir>:/w -e VUS=5 grafana/k6 run /w/load_k6.js
import http from 'k6/http'
import { sleep, check } from 'k6'
const TOKEN = open('/w/.token').trim()
const IDS = JSON.parse(open('/w/ids.json'))
const BASE = __ENV.BASE || 'http://host.docker.internal:8000'
export const options = { vus: Number(__ENV.VUS || 5), duration: '60s', summaryTrendStats: ['min', 'med', 'p(95)', 'max', 'count'],
  thresholds: { 'http_req_duration{view:dashboard}': ['p(95)<100000'], 'http_req_duration{view:document_list}': ['p(95)<100000'], 'http_req_duration{view:readiness}': ['p(95)<100000'] } }
export default function () {
  const r = Math.random()
  const h = { headers: { Authorization: `Bearer ${TOKEN}` } }
  let res
  if (r < 0.4) res = http.get(`${BASE}/api/dashboard`, { ...h, tags: { view: 'dashboard' } })
  else if (r < 0.7) res = http.get(`${BASE}/api/seafarers/${IDS.seafarer}/documents`, { ...h, tags: { view: 'document_list' } })
  else res = http.get(`${BASE}/api/assignments/${IDS.assignment}/readiness`, { ...h, tags: { view: 'readiness' } })
  check(res, { 'status 200': (x) => x.status === 200 })
  sleep(1)
}
