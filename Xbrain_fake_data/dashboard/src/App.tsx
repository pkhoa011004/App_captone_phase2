import { useState, useEffect } from 'react';
import { 
  Activity, 
  Terminal, 
  Network, 
  GitCommit, 
  Users, 
  Database, 
  FileCode, 
  ChevronRight, 
  ChevronDown, 
  ShieldAlert, 
  Cpu
} from 'lucide-react';

// Scenarios configuration
const SCENARIOS = [
  { id: '01_main_scenario', name: 'Main Scenario (Same-Service 10m)', desc: '5 distinct signals correlated on book-service' },
  { id: '02_with_duplicates', name: 'Duplicates & Replays', desc: 'Main scenario alerts with duplicate alert IDs' },
  { id: '03_with_invalid', name: 'With Invalid Alerts', desc: 'Main scenario with alerts missing tenant/env' },
  { id: '04_multiple_unsupported_groups', name: 'Multiple Services (Unsupported)', desc: 'Includes book-service & order-service alerts' },
  { id: '05_same_service_diff_namespace', name: 'Different Namespaces', desc: 'book-service alerts in prod vs staging' },
  { id: '06_same_service_diff_tenant', name: 'Different Tenants', desc: 'book-service alerts for tenant-a vs tenant-b' },
  { id: '07_same_service_diff_time_bucket', name: 'Different Time Buckets', desc: 'Alerts spanning across 10m boundaries' },
  { id: '08_severity_escalation', name: 'Severity Escalation', desc: 'Sequence of low -> medium -> critical warnings' },
  { id: '09_flapping_jitter', name: 'Noise Case: Flapping Latency & Ping', desc: 'Jitter/low warnings firing concurrently' },
  { id: '10_alert_storm_multiple_services', name: 'Noise Case: Alert Storm (4 Services)', desc: 'Storm from auth, payment, order & book services' },
  { id: '11_out_of_window', name: 'Noise Case: Out of Time Window', desc: 'Alert at 09:30 mixed with 10:00 alert' },
  { id: '12_missing_metadata', name: 'Noise Case: Missing Optional Metadata', desc: 'Valid grouping alert missing pod/deploy tags' },
  { id: '13_container_oomkilled', name: 'Scenario 2: Container OOMKilled', desc: 'Pod RAM overload leading to K8s SIGKILL and CrashLoop' },
  { id: '14_cpu_throttling', name: 'Scenario 6: CPU Throttling', desc: 'High CPU load leading to cgroups throttling and GC pauses' },
  { id: '15_api_5xx_spike', name: 'Scenario 3: API HTTP 5xx Rate Spike', desc: 'Buggy deployment v1.4.3 causing NullPointerException HTTP 500s' }
];

export default function App() {
  const [activeScenario, setActiveScenario] = useState('01_main_scenario');
  const [activeTab, setActiveTab] = useState('pipeline'); // 'pipeline' | 'observability' | 'triage'
  const [inputWrappers, setInputWrappers] = useState<any[]>([]);
  const [selectedAlertIdx, setSelectedAlertIdx] = useState<number>(0);
  const [simulatedIncident, setSimulatedIncident] = useState<any>(null);
  
  // Observability Data
  const [logs, setLogs] = useState<string>('');
  const [metrics, setMetrics] = useState<any[]>([]);
  const [traces, setTraces] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [deploy, setDeploy] = useState<any[]>([]);
  const [ownership, setOwnership] = useState<any>(null);
  
  // Future Mock Context
  const [evidenceBundle, setEvidenceBundle] = useState<any>(null);
  const [triageContext, setTriageContext] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Trace collapse state
  const [traceExpanded, setTraceExpanded] = useState(true);

  // Fetch data on scenario change
  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        // Fetch correlator input
        const inputRes = await fetch(`./fake-data/correlator-input/${activeScenario}.json`);
        if (!inputRes.ok) throw new Error(`Failed to load input for scenario: ${activeScenario}`);
        const inputs = await inputRes.json();
        setInputWrappers(inputs);
        setSelectedAlertIdx(0);

        // Fetch expected output (optional validation log)
        const expectedRes = await fetch(`./fake-data/expected-incident/${activeScenario}_incident.json`);
        if (expectedRes.ok) {
          await expectedRes.json();
        }

        // Run local browser pipeline simulation
        runBrowserPipeline(inputs);

        // Fetch logs
        const logPath = activeScenario === '13_container_oomkilled' ? './fake-data/evidence/logs/scenario_02_oomkilled_logs.json' :
                        activeScenario === '14_cpu_throttling' ? './fake-data/evidence/logs/scenario_06_cpu_throttling_logs.json' :
                        activeScenario === '15_api_5xx_spike' ? './fake-data/evidence/logs/scenario_03_api_5xx_spike_logs.json' :
                        './fake-data/evidence/logs/book-service.log';
        const logRes = await fetch(logPath);
        if (logRes.ok) {
          if (logPath.endsWith('.json')) {
            const logJson = await logRes.json();
            const logText = logJson.map((l: any) => `[${l.level.toUpperCase()}] ${l.ts} ${l.message}`).join('\n');
            setLogs(logText);
          } else {
            setLogs(await logRes.text());
          }
        }

        // Fetch metrics
        let fetchedMetrics: any[] = [];
        if (activeScenario === '13_container_oomkilled') {
          const res = await fetch('./fake-data/evidence/metrics/scenario_02_oomkilled_metrics.json');
          if (res.ok) fetchedMetrics = await res.json();
        } else if (activeScenario === '14_cpu_throttling') {
          const res = await fetch('./fake-data/evidence/metrics/scenario_06_cpu_throttling_metrics.json');
          if (res.ok) fetchedMetrics = await res.json();
        } else if (activeScenario === '15_api_5xx_spike') {
          const res = await fetch('./fake-data/evidence/metrics/scenario_03_api_5xx_spike_metrics.json');
          if (res.ok) fetchedMetrics = await res.json();
        } else {
          const metricFiles = [
            'http_5xx_rate', 'http_latency_p95_ms', 'memory_usage_mb', 
            'cpu_usage_percent', 'container_restart_count', 
            'kube_pod_container_status_waiting_reason'
          ];
          fetchedMetrics = (await Promise.all(
            metricFiles.map(async (name) => {
              const res = await fetch(`./fake-data/evidence/metrics/${name}.json`);
              return res.ok ? res.json() : null;
            })
          )).filter(Boolean);
        }
        const normalizedMetrics = Array.isArray(fetchedMetrics) ? fetchedMetrics : [fetchedMetrics];
        const mappedMetrics = normalizedMetrics.map((m: any) => {
          if (!m) return null;
          const valuesList = m.values || m.points || [];
          const mappedValues = valuesList.map((v: any) => ({
            value: v.value,
            timestamp: v.timestamp || v.ts
          }));
          return { ...m, values: mappedValues };
        }).filter(Boolean);
        setMetrics(mappedMetrics);

        // Fetch traces
        const traceRes = await fetch('./fake-data/evidence/traces/traces.json');
        if (traceRes.ok) setTraces(await traceRes.json());

        // Fetch events
        const eventPath = activeScenario === '13_container_oomkilled' ? './fake-data/evidence/k8s-events/scenario_02_oomkilled_events.json' :
                          activeScenario === '14_cpu_throttling' ? './fake-data/evidence/k8s-events/scenario_06_cpu_throttling_events.json' :
                          activeScenario === '15_api_5xx_spike' ? './fake-data/evidence/k8s-events/scenario_03_api_5xx_spike_events.json' :
                          './fake-data/evidence/k8s-events/events.json';
        const eventRes = await fetch(eventPath);
        if (eventRes.ok) {
          const rawEvents = await eventRes.json();
          const mappedEvents = rawEvents.map((e: any) => ({
            event_time: e.event_time || e.ts,
            type: e.type,
            reason: e.reason,
            object: e.object || `Pod/${e.pod || 'book-service-7d9f6c8d9f-abcd1'} (${e.container || 'book-service'})`,
            message: e.message
          }));
          setEvents(mappedEvents);
        }

        // Fetch deploy
        const deployPath = activeScenario === '15_api_5xx_spike' ? './fake-data/evidence/deploys/scenario_03_api_5xx_spike_deploys.json' :
                           './fake-data/evidence/deploys/deploy.json';
        const deployRes = await fetch(deployPath);
        if (deployRes.ok) setDeploy(await deployRes.json());

        // Fetch ownership
        const ownershipRes = await fetch('./fake-data/evidence/ownership/ownership.json');
        if (ownershipRes.ok) setOwnership(await ownershipRes.json());

        // Fetch evidence bundle
        const bundlePath = activeScenario === '13_container_oomkilled' ? './fake-data/expected-evidence-bundle/13_container_oomkilled_evidence.json' :
                           activeScenario === '14_cpu_throttling' ? './fake-data/expected-evidence-bundle/14_cpu_throttling_evidence.json' :
                           activeScenario === '15_api_5xx_spike' ? './fake-data/expected-evidence-bundle/15_api_5xx_spike_evidence.json' :
                           './fake-data/expected-evidence-bundle/evidence_bundle.json';
        const bundleRes = await fetch(bundlePath);
        if (bundleRes.ok) setEvidenceBundle(await bundleRes.json());

        // Fetch triage context
        const triagePath = activeScenario === '13_container_oomkilled' ? './fake-data/expected-triage-context/13_container_oomkilled_triage.json' :
                           activeScenario === '14_cpu_throttling' ? './fake-data/expected-triage-context/14_cpu_throttling_triage.json' :
                           activeScenario === '15_api_5xx_spike' ? './fake-data/expected-triage-context/15_api_5xx_spike_triage.json' :
                           './fake-data/expected-triage-context/triage_context.json';
        const triageRes = await fetch(triagePath);
        if (triageRes.ok) setTriageContext(await triageRes.json());

      } catch (err: any) {
        console.error(err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [activeScenario]);

  // Browser Simulation of Ingest & Correlator Logic
  function runBrowserPipeline(inputs: any[]) {
    // 1. Ingest Step
    // The inputs are already ingest wrappers, but we run the logic on them to simulate
    const validWrappers = inputs.filter(w => w.validation.status === 'VALID');

    // 2. Correlation Deduplication
    const seenAlertIds = new Set<string>();
    const dedupedWrappers: any[] = [];
    let duplicateCount = 0;

    for (const w of validWrappers) {
      const alertId = w.normalized_alert.alert_id;
      if (seenAlertIds.has(alertId)) {
        duplicateCount++;
      } else {
        seenAlertIds.add(alertId);
        dedupedWrappers.push(w);
      }
    }

    if (dedupedWrappers.length === 0) {
      setSimulatedIncident({
        status: "NO_ACTIVE_ALERTS",
        incident: null,
        group_keys: []
      });
      return;
    }

    // 3. Group Aggregation
    // Group Key: tenant_id:environment:cluster:namespace:service:10-minute-bucket
    const getBucketStart = (startedAt: string) => {
      const date = new Date(startedAt);
      const minutes = date.getUTCMinutes();
      const roundedMinutes = Math.floor(minutes / 10) * 10;
      date.setUTCMinutes(roundedMinutes);
      date.setUTCSeconds(0);
      date.setUTCMilliseconds(0);
      return date.toISOString().replace('.000Z', 'Z');
    };

    const groupMap = new Map<string, any[]>();
    for (const w of dedupedWrappers) {
      const na = w.normalized_alert;
      const bucketStart = getBucketStart(na.started_at);
      const groupKey = `${na.tenant_id}:${na.environment}:${na.cluster}:${na.namespace}:${na.service}:${bucketStart.replace(/[-T:Z]/g, '').slice(0, 12)}`;
      
      if (!groupMap.has(groupKey)) {
        groupMap.set(groupKey, []);
      }
      groupMap.get(groupKey)!.push(w);
    }

    const groupKeys = Array.from(groupMap.keys());

    // Boundary check: Multiple groups check
    if (groupKeys.length > 1) {
      setSimulatedIncident({
        status: "MULTIPLE_GROUPS_UNSUPPORTED",
        incident: null,
        group_keys: groupKeys
      });
      return;
    }

    // 4. Construct Incident for single group
    const activeGroupKey = groupKeys[0];
    const groupAlerts = groupMap.get(activeGroupKey)!;
    const representativeAlert = groupAlerts[0].normalized_alert;

    // Severity Escalation
    const severityHierarchy = ['unknown', 'low', 'medium', 'high', 'critical'];
    let highestSeverity = 'low';
    for (const w of groupAlerts) {
      const sev = w.normalized_alert.severity;
      if (severityHierarchy.indexOf(sev) > severityHierarchy.indexOf(highestSeverity)) {
        highestSeverity = sev;
      }
    }

    // Extract Signals
    const extractSignal = (title: string, desc: string) => {
      const checkText = `${title} ${desc}`.toLowerCase();
      if (checkText.includes('5xx') || checkText.includes('status_code 5xx')) return 'http_5xx_high';
      if (checkText.includes('latency')) return 'latency_high';
      if (checkText.includes('healthcheck') || checkText.includes('health') || checkText.includes('blackbox') || checkText.includes('ping')) return 'healthcheck_failed';
      if (checkText.includes('crashloopbackoff') || checkText.includes('crashloop')) return 'pod_crashloop';
      if (checkText.includes('restart')) return 'container_restart';
      if (checkText.includes('timeout')) return 'timeout';
      if (checkText.includes('oom')) return 'oom_killed';
      if (checkText.includes('memory_usage_high') || checkText.includes('memory') || checkText.includes('ram')) return 'memory_usage_high';
      if (checkText.includes('throttle') || checkText.includes('throttled')) return 'cpu_throttled';
      if (checkText.includes('cpu')) return 'cpu_usage_high';
      return 'unknown_signal';
    };

    const signals = Array.from(new Set(groupAlerts.map(w => 
      extractSignal(w.normalized_alert.title, w.normalized_alert.description)
    )));

    // Related entities
    const pods = Array.from(new Set(groupAlerts.map(w => w.normalized_alert.labels.pod).filter(Boolean)));
    const deployments = Array.from(new Set(groupAlerts.map(w => w.normalized_alert.labels.deployment).filter(Boolean)));
    const containers = Array.from(new Set(groupAlerts.map(w => w.normalized_alert.labels.container).filter(Boolean)));

    // Time window
    const timestamps = groupAlerts.map(w => new Date(w.normalized_alert.started_at).getTime());
    const minTime = new Date(Math.min(...timestamps)).toISOString();
    const maxTime = new Date(Math.max(...timestamps)).toISOString();

    // format bucket start
    const bucketStartFormatted = `${representativeAlert.started_at.slice(0, 14)}00:00Z`;

    const incident = {
      incident_id: `inc-${representativeAlert.tenant_id}-${representativeAlert.environment}-${representativeAlert.service}-${activeGroupKey.split(':').pop()}`,
      correlation_id: `corr-${representativeAlert.tenant_id}-${representativeAlert.environment}-${representativeAlert.service}-${activeGroupKey.split(':').pop()}`,
      group_key: activeGroupKey.replace(/:(\d{12})$/, () => {
        // format bucket to match
        return `:${representativeAlert.started_at.slice(0, 14)}00:00Z`;
      }),
      bucket_start: bucketStartFormatted,
      tenant_id: representativeAlert.tenant_id,
      environment: representativeAlert.environment,
      cluster: representativeAlert.cluster,
      namespace: representativeAlert.namespace,
      service: representativeAlert.service,
      severity: highestSeverity,
      status: "ACTIVE",
      correlation_metadata: {
        total_alerts: inputs.length,
        first_alert_received: inputs[0].received_at,
        last_alert_received: inputs[inputs.length - 1].received_at,
        correlation_rules_applied: ["same-service-10m-bucket"]
      },
      alerts: groupAlerts.map(w => w.normalized_alert),
      alert_ids: groupAlerts.map(w => w.normalized_alert.alert_id),
      deduped_alert_ids: groupAlerts.map(w => w.normalized_alert.alert_id),
      signals: signals,
      related_entities: {
        deployments,
        pods,
        containers
      },
      time_window: {
        start: minTime,
        end: maxTime
      },
      next_step: "BUILD_EVIDENCE"
    };

    setSimulatedIncident({
      status: "CORRELATED",
      incident
    });
  }

  // Helper for rendering line graph SVGs
  const renderSVGChart = (metric: any, strokeColor: string, key: any) => {
    if (!metric || !metric.values || metric.values.length === 0) return null;
    const values = metric.values.map((v: any) => v.value);
    const maxVal = Math.max(...values, 1);
    const minVal = Math.min(...values, 0);
    const range = maxVal - minVal;
    
    const width = 500;
    const height = 180;
    const padding = 20;

    const points = metric.values.map((v: any, idx: number) => {
      const x = padding + (idx * (width - padding * 2)) / (metric.values.length - 1);
      const y = height - padding - ((v.value - minVal) * (height - padding * 2)) / range;
      return { x, y, ...v };
    });

    const pathD = points.reduce((acc: string, p: any, idx: number) => {
      return idx === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`;
    }, '');

    // Area path d
    const areaD = `${pathD} L ${points[points.length - 1].x} ${height - padding} L ${points[0].x} ${height - padding} Z`;

    return (
      <div className="chart-container" key={key}>
        <div className="chart-header">
          <span className="chart-title">{metric.metric_name}</span>
          <span className="chart-value" style={{ color: strokeColor }}>
            {values[values.length - 1].toFixed(2)}
          </span>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
          {/* Grids */}
          <line x1={padding} y1={padding} x2={width - padding} y2={padding} stroke="#1c2030" strokeDasharray="3" />
          <line x1={padding} y1={height / 2} x2={width - padding} y2={height / 2} stroke="#1c2030" strokeDasharray="3" />
          <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#23283c" />

          {/* Area fill */}
          <path d={areaD} fill={`url(#gradient-${metric.metric_name})`} opacity="0.1" />

          {/* Path line */}
          <path d={pathD} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" />

          {/* Points */}
          {points.map((p: any, idx: number) => {
            // only draw dots for spikes or key times
            if (idx === 15 || idx === 17 || idx === points.length - 1 || p.value > maxVal * 0.7) {
              return (
                <circle key={idx} cx={p.x} cy={p.y} r="3" fill="#ffffff" stroke={strokeColor} strokeWidth="1.5" />
              );
            }
            return null;
          })}

          {/* Gradients definitions */}
          <defs>
            <linearGradient id={`gradient-${metric.metric_name}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    );
  };

  const currentAlertWrapper = inputWrappers[selectedAlertIdx];
  const isCorrelated = simulatedIncident?.status === 'CORRELATED';

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-title-group">
          <h1>CDO Pipeline Simulator & Observability Dashboard</h1>
          <p>Mô phỏng CDO Ingest Lambda & Same-Service Correlator (Phase 2 MVP)</p>
        </div>

        <div className="scenario-select-container">
          <span className="text-sm font-semibold text-gray-400">Chọn kịch bản test:</span>
          <select 
            value={activeScenario}
            onChange={(e) => setActiveScenario(e.target.value)}
            className="scenario-select"
          >
            {SCENARIOS.map((scen) => (
              <option key={scen.id} value={scen.id}>
                {scen.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Tabs Menu */}
      <div className="px-8 mt-4">
        <div className="tabs-container">
          <button 
            className={`tab-button ${activeTab === 'pipeline' ? 'active' : ''}`}
            onClick={() => setActiveTab('pipeline')}
          >
            <Network className="inline w-4 h-4 mr-2" />
            Pipeline Ingest & Correlator
          </button>
          <button 
            className={`tab-button ${activeTab === 'observability' ? 'active' : ''}`}
            onClick={() => setActiveTab('observability')}
            disabled={!isCorrelated && activeScenario !== '01_main_scenario'}
            style={{ opacity: !isCorrelated && activeScenario !== '01_main_scenario' ? 0.5 : 1 }}
          >
            <Activity className="inline w-4 h-4 mr-2" />
            Observability Timeline (Evidence)
          </button>
          <button 
            className={`tab-button ${activeTab === 'triage' ? 'active' : ''}`}
            onClick={() => setActiveTab('triage')}
          >
            <FileCode className="inline w-4 h-4 mr-2" />
            AIOps Triage Context (Future)
          </button>
        </div>
      </div>

      {/* Main Grid Workspace */}
      <main className="main-content">
        {loading ? (
          <div className="flex items-center justify-center col-span-2 h-96">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500 mx-auto mb-4"></div>
              <p className="text-gray-400">Đang tải dữ liệu kịch bản...</p>
            </div>
          </div>
        ) : error ? (
          <div className="col-span-2 bg-red-950/20 border border-red-900/50 p-6 rounded-lg text-center">
            <ShieldAlert className="w-12 h-12 text-red-500 mx-auto mb-2" />
            <h3 className="text-red-400 font-bold mb-1">Đã xảy ra lỗi</h3>
            <p className="text-red-300 text-sm">{error}</p>
          </div>
        ) : (
          <>
            {/* Left sidebar: Alerts in Input Queue */}
            <div className="flex flex-col gap-4">
              <div className="card">
                <div className="card-header">
                  <h3 className="card-title">
                    <Database className="w-4 h-4 text-indigo-400" />
                    Input Alerts ({inputWrappers.length})
                  </h3>
                  <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded text-slate-400">RAW QUEUE</span>
                </div>
                <div className="alert-list">
                  {inputWrappers.map((wrapper, idx) => {
                    const alert = wrapper.normalized_alert || {
                      title: "Invalid Raw Alert Format",
                      service: "unknown",
                      severity: "unknown"
                    };
                    const isSelected = selectedAlertIdx === idx;
                    const isValid = wrapper.validation.status === 'VALID';
                    
                    return (
                      <div 
                        key={idx} 
                        className={`alert-item ${isSelected ? 'active' : ''}`}
                        onClick={() => setSelectedAlertIdx(idx)}
                      >
                        <div className="alert-item-header">
                          <span className="alert-item-service">{alert.service}</span>
                          <span className={`badge ${isValid ? `badge-${alert.severity}` : 'badge-critical'}`}>
                            {isValid ? alert.severity : 'INVALID'}
                          </span>
                        </div>
                        <h4 className="alert-item-title text-slate-200">{alert.title}</h4>
                        <div className="flex justify-between items-center mt-2 text-[10px] text-gray-500">
                          <span>{new Date(wrapper.received_at).toLocaleTimeString()}</span>
                          <span>ID: {alert.alert_id?.slice(0, 18) || "N/A"}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="card">
                <h3 className="card-title text-sm mb-3">Thông tin Kịch bản</h3>
                <p className="text-xs text-gray-400">
                  {SCENARIOS.find(s => s.id === activeScenario)?.desc}
                </p>
                <div className="border-t border-slate-800/80 mt-3 pt-3 flex flex-col gap-2 text-xs text-slate-400">
                  <div className="flex justify-between">
                    <span>Tenant ID:</span>
                    <span className="font-semibold text-slate-200">tenant-a</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Môi trường:</span>
                    <span className="font-semibold text-slate-200">prod</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Cluster:</span>
                    <span className="font-semibold text-slate-200">eks-prod</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Service đích:</span>
                    <span className="font-semibold text-indigo-400">book-service</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Main Panel */}
            <div className="pipeline-dashboard">
              
              {activeTab === 'pipeline' && (
                <div className="pipeline-flow">
                  {/* Ingest Phase Simulation */}
                  <div className="card">
                    <div className="card-header">
                      <h3 className="card-title">
                        <Cpu className="w-4 h-4 text-emerald-400" />
                        Phase 1: Ingest Lambda (Chuẩn hóa)
                      </h3>
                      {currentAlertWrapper?.validation.status === 'VALID' ? (
                        <span className="badge badge-success">VALID</span>
                      ) : (
                        <span className="badge badge-critical">INVALID_ALERT</span>
                      )}
                    </div>
                    
                    <div className="flex flex-col gap-3">
                      <div className="text-xs text-slate-400">
                        {currentAlertWrapper?.validation.status === 'VALID' ? (
                          <p>✓ Siêu dữ liệu được tách thành các trường top-level. Không trùng lặp nhãn. Độ nghiêm trọng được map thành công.</p>
                        ) : (
                          <div className="bg-red-950/20 border border-red-900/30 p-2.5 rounded text-red-300">
                            <strong>Lỗi Validation:</strong> Thiếu trường bắt buộc trong Raw Alert labels:
                            <ul className="list-disc list-inside mt-1 font-semibold">
                              {currentAlertWrapper?.validation.missing_fields.map((f: string) => (
                                <li key={f}>{f}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>

                      <div className="text-xs font-semibold text-gray-400 mt-2">DỮ LIỆU INGEST OUTPUT WRAPPER:</div>
                      <pre className="code-viewer">
                        {JSON.stringify(currentAlertWrapper, null, 2)}
                      </pre>
                    </div>
                  </div>

                  {/* Same-Service Correlator Simulation */}
                  <div className="card">
                    <div className="card-header">
                      <h3 className="card-title">
                        <Network className="w-4 h-4 text-indigo-400" />
                        Phase 2: Same-Service Correlator
                      </h3>
                      {simulatedIncident?.status === 'CORRELATED' ? (
                        <span className="badge badge-success">CORRELATED</span>
                      ) : (
                        <span className="badge badge-critical">UNSUPPORTED_GROUPS</span>
                      )}
                    </div>

                    <div className="flex flex-col gap-3">
                      {simulatedIncident?.status === 'CORRELATED' ? (
                        <div className="flex flex-col gap-2">
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <div className="bg-slate-900/50 p-2 rounded">
                              <div className="text-[10px] text-gray-500">INCIDENT ID</div>
                              <div className="font-mono font-bold text-slate-200">{simulatedIncident.incident.incident_id}</div>
                            </div>
                            <div className="bg-slate-900/50 p-2 rounded">
                              <div className="text-[10px] text-gray-500">SEVERITY ĐƯỢC LÊN CẤP</div>
                              <div className="font-bold flex items-center gap-1 mt-0.5">
                                <span className={`badge badge-${simulatedIncident.incident.severity}`}>
                                  {simulatedIncident.incident.severity}
                                </span>
                              </div>
                            </div>
                          </div>
                          
                          <div className="text-xs bg-slate-900/30 p-2 rounded border border-slate-800">
                            <div className="text-[10px] text-gray-500 mb-1">TÍN HIỆU ĐƯỢC TRÍCH XUẤT (SIGNALS)</div>
                            <div className="flex flex-wrap gap-1">
                              {simulatedIncident.incident.signals.map((sig: string) => (
                                <span key={sig} className="bg-indigo-950/30 border border-indigo-900/50 text-indigo-300 text-[10px] px-2 py-0.5 rounded font-mono">
                                  {sig}
                                </span>
                              ))}
                            </div>
                          </div>

                          <div className="text-xs text-gray-400 mt-2">DỮ LIỆU INCIDENT OUTPUT:</div>
                          <pre className="code-viewer" style={{ maxHeight: '180px' }}>
                            {JSON.stringify(simulatedIncident, null, 2)}
                          </pre>
                        </div>
                      ) : (
                        <div className="flex flex-col gap-2">
                          <div className="bg-red-950/25 border border-red-900/30 p-3 rounded text-red-300 text-xs">
                            <strong>Trạng thái lỗi: MULTIPLE_GROUPS_UNSUPPORTED</strong>
                            <p className="mt-1 text-gray-400">Correlator phát hiện nhiều hơn một khoá nhóm sự cố trong cùng một lần quét. Phase 2 chỉ hỗ trợ xử lý 1 nhóm same-service duy nhất.</p>
                            <div className="mt-2.5">
                              <div className="text-[10px] text-red-400 font-bold mb-1 font-mono">MÃ NHÓM PHÁT HIỆN:</div>
                              <ul className="flex flex-col gap-1 font-mono text-[10px] bg-black/30 p-2 rounded text-red-200">
                                {simulatedIncident?.group_keys.map((key: string) => (
                                  <li key={key}>• {key}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'observability' && (
                <div className="flex flex-col gap-4">
                  {/* Metrics Row */}
                  <div className="card">
                    <div className="card-header">
                      <h3 className="card-title">
                        <Activity className="w-4 h-4 text-indigo-400" />
                        Dữ liệu Metrics (Từ 09:45 đến 10:10)
                      </h3>
                      <span className="text-[10px] text-gray-500">MỐC SỰ CỐ: 10:00 - 10:05</span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                      {metrics.map((metric, idx) => {
                        const colors = ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#a855f7', '#6366f1'];
                        return renderSVGChart(metric, colors[idx % colors.length], metric.metric_name);
                      })}
                    </div>
                  </div>

                  {/* Logs & Events split layout */}
                  <div className="obs-timeline-grid split">
                    {/* Log Viewer Card */}
                    <div className="card">
                      <div className="card-header">
                        <h3 className="card-title">
                          <Terminal className="w-4 h-4 text-emerald-400" />
                          Nhật ký Ứng dụng (book-service.log)
                        </h3>
                        <span className="text-[10px] text-gray-500">DƯỚI 50 DÒNG</span>
                      </div>
                      
                      <div className="log-stream">
                        {logs.split('\n').map((line, idx) => {
                          let lineClass = 'log-line';
                          if (line.includes('WARN')) lineClass += ' warn';
                          else if (line.includes('FATAL')) lineClass += ' fatal';
                          else if (line.includes('ERROR')) lineClass += ' error';
                          else if (line.includes('INFO')) lineClass += ' info';
                          
                          if (!line.trim()) return null;
                          return (
                            <div key={idx} className={lineClass}>
                              <span className="text-slate-600 mr-2 select-none">{(idx + 1).toString().padStart(2, '0')}</span>
                              {line}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* K8s Events Card */}
                    <div className="card">
                      <div className="card-header">
                        <h3 className="card-title">
                          <ShieldAlert className="w-4 h-4 text-red-400" />
                          Kubernetes Events
                        </h3>
                      </div>
                      <div className="event-timeline">
                        {events.map((evt, idx) => (
                          <div key={idx} className={`event-card ${evt.type}`}>
                            <div className="event-meta">
                              <span className="font-mono text-slate-500">{evt.event_time.slice(11, 19)}</span>
                              <span className={`badge ${evt.type === 'Warning' ? 'badge-critical' : 'badge-low'}`}>
                                {evt.reason}
                              </span>
                            </div>
                            <div className="text-gray-400 font-semibold text-[11px] mb-0.5">{evt.object}</div>
                            <div className="event-msg text-slate-200">{evt.message}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Traces, Deployments, Ownership */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {/* Trace card */}
                    <div className="card">
                      <div className="card-header">
                        <h3 className="card-title">
                          <Network className="w-4 h-4 text-purple-400" />
                          Phân tích Spans Trace
                        </h3>
                        <button 
                          onClick={() => setTraceExpanded(!traceExpanded)}
                          className="text-gray-500 hover:text-white"
                        >
                          {traceExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                        </button>
                      </div>

                      {traceExpanded && traces.map((trace, idx) => (
                        <div key={idx} className="text-xs bg-slate-950 p-3 rounded border border-slate-900">
                          <div className="flex justify-between text-gray-500 mb-2 font-mono text-[10px]">
                            <span>TRACE ID: {trace.trace_id}</span>
                            <span className="text-red-400 font-bold">ERROR IN SPAN</span>
                          </div>
                          
                          {/* Parent Span */}
                          <div className="flex items-center justify-between p-2 bg-red-950/20 border-l-2 border-red-500 rounded-r mb-2">
                            <div>
                              <div className="font-bold text-slate-200">{trace.root_span.operation}</div>
                              <div className="text-[10px] text-gray-500">{trace.root_span.service}</div>
                            </div>
                            <div className="text-right">
                              <div className="font-mono text-red-300 font-bold">{trace.root_span.duration_ms}ms</div>
                              <div className="text-[10px] bg-red-900/40 px-1 rounded text-red-200 font-mono">500</div>
                            </div>
                          </div>

                          {/* Child Spans */}
                          <div className="pl-6 border-l border-slate-800 flex flex-col gap-2">
                            {trace.child_spans.map((child: any, cidx: number) => (
                              <div key={cidx} className="flex items-center justify-between p-2 bg-slate-900 border-l-2 border-orange-500 rounded-r">
                                <div>
                                  <div className="font-bold text-slate-300">{child.operation}</div>
                                  <div className="text-[10px] text-gray-500">{child.service}</div>
                                </div>
                                <div className="text-right">
                                  <div className="font-mono text-orange-300">{child.duration_ms}ms</div>
                                  <div className="text-[9px] text-red-400 font-mono">{child.tags["error.message"]}</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Deploy & Ownership metadata */}
                    <div className="flex flex-col gap-4">
                      {/* Deployment Info */}
                      <div className="card flex-1">
                        <div className="card-header">
                          <h3 className="card-title">
                            <GitCommit className="w-4 h-4 text-blue-400" />
                            Thay đổi Triển khai (Deployments)
                          </h3>
                          <span className="text-[10px] bg-blue-950 border border-blue-900 text-blue-300 px-2 py-0.5 rounded font-mono">v1.2.3</span>
                        </div>

                        {deploy.map((dep, idx) => (
                          <div key={idx} className="text-xs flex flex-col gap-2">
                            <div className="bg-slate-900/60 p-2.5 rounded border border-slate-800">
                              <div className="text-[10px] text-gray-500">MÔ TẢ THAY ĐỔI</div>
                              <div className="font-semibold text-slate-200 mt-0.5">{dep.change_summary}</div>
                            </div>

                            <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                              <div>
                                <span>Deployed By:</span>
                                <span className="font-mono text-slate-200 block">{dep.deployed_by}</span>
                              </div>
                              <div>
                                <span>Thời gian deploy:</span>
                                <span className="font-mono text-slate-200 block">{new Date(dep.deployed_at).toLocaleString()}</span>
                              </div>
                              <div className="col-span-2">
                                <span>Git Commit SHA:</span>
                                <span className="font-mono text-indigo-400 block break-all">{dep.git_sha}</span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Ownership & Runbooks */}
                      <div className="card flex-1">
                        <div className="card-header">
                          <h3 className="card-title">
                            <Users className="w-4 h-4 text-indigo-400" />
                            Ownership & Runbooks
                          </h3>
                        </div>

                        {ownership && (
                          <div className="text-xs flex flex-col gap-2">
                            <div className="grid grid-cols-2 gap-2 text-slate-400">
                              <div>
                                <span className="block text-[10px] text-gray-500">ĐỘI NGŨ SỞ HỮU</span>
                                <span className="text-slate-200 font-semibold text-xs">{ownership.owner_team}</span>
                              </div>
                              <div>
                                <span className="block text-[10px] text-gray-500">SLACK CHANNEL</span>
                                <span className="text-indigo-400 font-mono text-xs">{ownership.slack_channel}</span>
                              </div>
                            </div>

                            <div className="mt-2 border-t border-slate-850 pt-2">
                              <span className="block text-[10px] text-gray-500 mb-1">RUNBOOKS CỦA HỆ THỐNG</span>
                              <div className="flex flex-col gap-1.5">
                                {ownership.runbooks.map((rb: any, idx: number) => (
                                  <a 
                                    key={idx} 
                                    href="#" 
                                    onClick={(e) => e.preventDefault()}
                                    className="bg-slate-900 hover:bg-slate-850 border border-slate-800 p-2 rounded flex justify-between items-center text-indigo-300 font-semibold no-underline"
                                  >
                                    <span>{rb.trigger_reason}</span>
                                    <span className="text-[10px] text-gray-500 font-mono">{rb.runbook_url}</span>
                                  </a>
                                ))}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'triage' && (
                <div className="pipeline-flow">
                  {/* Evidence Bundle */}
                  <div className="card">
                    <div className="card-header">
                      <h3 className="card-title">
                        <Database className="w-4 h-4 text-yellow-400" />
                        Expected Evidence Bundle (Đầu ra gom bằng chứng)
                      </h3>
                      <span className="badge badge-success">COMPLETE</span>
                    </div>
                    <div className="flex flex-col gap-3">
                      <p className="text-xs text-gray-400">Bằng chứng hoàn chỉnh chứa thông tin liên kết logs, traces, metrics, deployments và events trong khung thời gian 25 phút.</p>
                      <pre className="code-viewer" style={{ maxHeight: '420px' }}>
                        {JSON.stringify(evidenceBundle, null, 2)}
                      </pre>
                    </div>
                  </div>

                  {/* Triage Context */}
                  <div className="card">
                    <div className="card-header">
                      <h3 className="card-title">
                        <FileCode className="w-4 h-4 text-indigo-400" />
                        Expected Triage Context (Mẫu đầu vào cho AIOps)
                      </h3>
                      <span className="text-[10px] text-gray-500">S3 POINTER FORMAT</span>
                    </div>
                    <div className="flex flex-col gap-3">
                      <p className="text-xs text-gray-400">Ngữ cảnh truyền đi gọn nhẹ dưới dạng liên kết S3 trỏ tới Evidence Bundle đầy đủ để giảm chi phí mạng và tránh quá tải API.</p>
                      <pre className="code-viewer" style={{ maxHeight: '420px' }}>
                        {JSON.stringify(triageContext, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
              )}

            </div>
          </>
        )}
      </main>
    </div>
  );
}
