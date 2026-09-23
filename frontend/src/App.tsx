import { useEffect, useRef, useState } from 'react'
import {
  Room,
  RoomEvent,
  Track,
  RemoteTrack,
  RemoteTrackPublication,
  RemoteParticipant,
} from 'livekit-client'
import {
  Mic,
  MicOff,
  PhoneCall,
  PhoneOff,
  Radio,
  Zap,
  Volume2,
  Clock,
  Building2,
  ShieldAlert,
  Compass,
  Activity,
  AlertCircle,
  BarChart3,
  RefreshCw,
  History,
} from 'lucide-react'

interface TranscriptTurn {
  id: string
  role: 'user' | 'agent'
  text: string
  timestamp: string
}

interface DomainEventPayload {
  event_id: string
  event_type: string
  timestamp: string
  payload: Record<string, any>
  duration_ms?: number
  tool_name?: string
}

interface LatencyMetrics {
  t_turn_eou_ms?: number
  t_stt_ms?: number
  t_llm_ttft_ms?: number
  t_llm_total_ms?: number
  t_tts_ttfb_ms?: number
  t_tts_total_ms?: number
  t_total_reconstructed_ms?: number
}

interface SystemHealth {
  status: string
  livekit: boolean
  ollama: boolean
  kokoro: boolean
}

interface PendingActionState {
  action_type: string
  property_id?: string
  property_title?: string
  date?: string
  time?: string
  renter_name?: string
  summary: string
  booking_id?: string
}

interface ActivePropertyState {
  property_id: string
  title: string
  address?: string
  monthly_rent?: number
  bedrooms?: number
  bathrooms?: number
  square_feet?: number
  neighborhood?: string
}

interface StructuredErrorItem {
  error_id: string
  code: string
  message: string
  timestamp: string
  workflow_id?: string
}

interface MetricsSummaryData {
  summary_timestamp?: string
  sample_counts?: {
    total_sessions?: number
    total_turns?: number
    cold_start_turns?: number
    warm_runtime_turns?: number
    total_errors?: number
  }
  workflows?: {
    total_workflows?: number
    completed?: number
    abandoned?: number
    completion_rate_pct?: number
  }
  latency?: {
    warm_turns?: {
      t_stt_ms?: any
      t_llm_ttft_ms?: any
      t_tts_ttfb_ms?: any
      t_turn_total_ms?: any
    }
  }
  error_taxonomy?: Record<string, number>
}

export default function App() {
  const [userName, setUserName] = useState<string>('Alex')
  const [connectionState, setConnectionState] = useState<
    'disconnected' | 'connecting' | 'connected'
  >('disconnected')
  const [isMicMuted, setIsMicMuted] = useState<boolean>(false)
  const [voiceState, setVoiceState] = useState<string>('DISCONNECTED')
  const [workflowState, setWorkflowState] = useState<string>('IDLE')
  const [activeProperty, setActiveProperty] = useState<ActivePropertyState | null>(null)
  const [pendingAction, setPendingAction] = useState<PendingActionState | null>(null)
  const [activeTool, setActiveTool] = useState<string | null>(null)
  const [transcripts, setTranscripts] = useState<TranscriptTurn[]>([])
  const [events, setEvents] = useState<DomainEventPayload[]>([])
  const [latency, setLatency] = useState<LatencyMetrics | null>(null)
  const [activeTab, setActiveTab] = useState<'live' | 'observability' | 'replay'>('live')
  const [activeWorkflowId, setActiveWorkflowId] = useState<string | null>(null)
  const [workflowTransitions, setWorkflowTransitions] = useState<string[]>(['IDLE'])
  const [structuredErrors, setStructuredErrors] = useState<StructuredErrorItem[]>([])
  const [apiMetricsSummary, setApiMetricsSummary] = useState<MetricsSummaryData | null>(null)
  const [replayingEvents, setReplayingEvents] = useState<DomainEventPayload[]>([])
  const [replayFilter, setReplayFilter] = useState<string>('')
  const seenEventIdsRef = useRef<Set<string>>(new Set())
  const [health, setHealth] = useState<SystemHealth>({
    status: 'checking',
    livekit: false,
    ollama: false,
    kokoro: false,
  })

  const roomRef = useRef<Room | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement>(null)

  // Poll service health
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/health')
        if (res.ok) {
          const data = await res.json()
          setHealth(data)
        }
      } catch (e) {
        setHealth({ status: 'offline', livekit: false, ollama: false, kokoro: false })
      }
    }
    checkHealth()
    const timer = setInterval(checkHealth, 5000)
    return () => clearInterval(timer)
  }, [])

  const fetchMetricsSummary = async () => {
    try {
      const res = await fetch('/api/metrics/summary')
      if (res.ok) {
        const data = await res.json()
        setApiMetricsSummary(data)
      }
    } catch (e) {
      console.error('Error fetching metrics summary:', e)
    }
  }

  const fetchReplayEvents = async () => {
    try {
      const url = replayFilter.trim()
        ? `/api/events?event_type=${encodeURIComponent(replayFilter.trim())}`
        : '/api/events'
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        setReplayingEvents(data)
      }
    } catch (e) {
      console.error('Error fetching replay events:', e)
    }
  }

  useEffect(() => {
    if (activeTab === 'observability') {
      fetchMetricsSummary()
    } else if (activeTab === 'replay') {
      fetchReplayEvents()
    }
  }, [activeTab])

  // Auto-scroll transcripts
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcripts])

  const handleConnect = async () => {
    if (connectionState !== 'disconnected') return
    setConnectionState('connecting')
    setVoiceState('CONNECTING')

    try {
      // 1. Obtain token from server-side token API
      const tokenRes = await fetch('/api/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: userName.trim() || 'Renter' }),
      })

      if (!tokenRes.ok) {
        throw new Error(`Token service responded with status ${tokenRes.status}`)
      }

      const { token, url } = await tokenRes.json()

      // 2. Initialize LiveKit WebRTC room
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      })
      roomRef.current = room

      // Handle subscribed agent audio track
      room.on(
        RoomEvent.TrackSubscribed,
        (
          track: RemoteTrack,
          _publication: RemoteTrackPublication,
          participant: RemoteParticipant
        ) => {
          if (track.kind === Track.Kind.Audio) {
            const audioElement = track.attach()
            audioElement.id = `audio-${participant.identity}`
            document.body.appendChild(audioElement)
          }
        }
      )

      room.on(
        RoomEvent.TrackUnsubscribed,
        (track: RemoteTrack) => {
          track.detach().forEach((el) => el.remove())
        }
      )

      // Handle reliable data packets on topic 'proprelay.events'
      room.on(
        RoomEvent.DataReceived,
        (payload: Uint8Array) => {
          try {
            const text = new TextDecoder().decode(payload)
            const event: DomainEventPayload = JSON.parse(text)

            // WebRTC Deduplication Gate (TDR-035)
            if (event.event_id && seenEventIdsRef.current.has(event.event_id)) {
              return
            }
            if (event.event_id) {
              seenEventIdsRef.current.add(event.event_id)
            }

            // Track workflow ID
            const wfId = (event as any).workflow_id || event.payload?.workflow_id
            if (wfId) {
              setActiveWorkflowId(wfId)
            }

            // Track structured errors
            if (
              event.event_type.includes('error') ||
              event.event_type.includes('failed') ||
              event.event_type.includes('rejected')
            ) {
              const code = event.payload?.error_code || 'TOOL_ERROR'
              const msg =
                event.payload?.reason ||
                event.payload?.message ||
                event.payload?.error ||
                'Operational error'
              setStructuredErrors((prev) => [
                {
                  error_id: event.event_id || String(Date.now()),
                  code: String(code),
                  message: String(msg),
                  timestamp: new Date(event.timestamp).toLocaleTimeString(),
                  workflow_id: wfId,
                },
                ...prev.slice(0, 19),
              ])
            }

            // Add to live events feed (retain last 50)
            setEvents((prev) => [event, ...prev.slice(0, 49)])

            // React to voice runtime events
            if (event.event_type === 'voice.state.changed') {
              setVoiceState(event.payload.new_state || 'LISTENING')
            } else if (event.event_type === 'voice.transcript.user') {
              const text = event.payload.transcript
              if (text && event.payload.is_final) {
                setTranscripts((prev) => [
                  ...prev,
                  {
                    id: event.event_id,
                    role: 'user',
                    text,
                    timestamp: new Date(event.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    }),
                  },
                ])
              }
            } else if (event.event_type === 'voice.transcript.agent') {
              const text = event.payload.transcript
              if (text) {
                setTranscripts((prev) => [
                  ...prev,
                  {
                    id: event.event_id,
                    role: 'agent',
                    text,
                    timestamp: new Date(event.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    }),
                  },
                ])
              }
            } else if (event.event_type === 'voice.latency.metrics') {
              setLatency(event.payload as LatencyMetrics)
            } else if (event.event_type === 'agent.tool.started') {
              setActiveTool(event.tool_name || 'Executing Tool...')
            } else if (event.event_type === 'agent.tool.completed') {
              setActiveTool(null)
            } else if (event.event_type === 'agent.tool.failed') {
              setActiveTool(null)
            } else if (event.event_type === 'workflow.state.changed') {
              if (event.payload.new_state) {
                setWorkflowState(event.payload.new_state)
                setWorkflowTransitions((prev) => [...prev.slice(-9), event.payload.new_state])
              }
            } else if (event.event_type === 'booking.confirmation.requested') {
              setWorkflowState('AWAITING_BOOKING_CONFIRMATION')
              setPendingAction({
                action_type: 'BOOK_SHOWING',
                property_id: event.payload.property_id,
                property_title: event.payload.property_title,
                date: event.payload.date,
                time: event.payload.time,
                renter_name: event.payload.renter_name,
                summary: event.payload.summary || 'Showing booking confirmation requested.',
              })
            } else if (event.event_type === 'showing.reschedule.requested') {
              setWorkflowState('AWAITING_BOOKING_CONFIRMATION')
              setPendingAction({
                action_type: 'RESCHEDULE_SHOWING',
                booking_id: event.payload.booking_id,
                date: event.payload.date,
                time: event.payload.time,
                renter_name: event.payload.renter_name,
                summary: event.payload.summary || 'Reschedule confirmation requested.',
              })
            } else if (event.event_type === 'showing.cancellation.requested') {
              setWorkflowState('AWAITING_BOOKING_CONFIRMATION')
              setPendingAction({
                action_type: 'CANCEL_SHOWING',
                booking_id: event.payload.booking_id,
                renter_name: event.payload.renter_name,
                summary: event.payload.summary || 'Cancellation confirmation requested.',
              })
            } else if (
              event.event_type === 'booking.confirmation.accepted' ||
              event.event_type === 'showing.booked' ||
              event.event_type === 'showing.rescheduled'
            ) {
              setPendingAction(null)
              setWorkflowState('BOOKED')
            } else if (
              event.event_type === 'booking.confirmation.declined' ||
              event.event_type === 'showing.cancelled'
            ) {
              setPendingAction(null)
              setWorkflowState('IDLE')
            } else if (event.event_type === 'property.details.viewed') {
              if (event.payload.property) {
                setActiveProperty(event.payload.property as ActivePropertyState)
              }
              setWorkflowState('PROPERTY_SELECTED')
            } else if (event.event_type === 'property.search.completed') {
              setWorkflowState('REVIEWING_RESULTS')
            } else if (event.event_type === 'showing.availability.checked') {
              setWorkflowState('CHECKING_AVAILABILITY')
            }
          } catch (err) {
            console.error('Error parsing data packet:', err)
          }
        }
      )

      room.on(RoomEvent.Disconnected, () => {
        setConnectionState('disconnected')
        setVoiceState('DISCONNECTED')
        setActiveTool(null)
      })

      // Connect to LiveKit Room
      await room.connect(url, token)
      setConnectionState('connected')
      setVoiceState('LISTENING')

      // Publish local microphone
      await room.localParticipant.setMicrophoneEnabled(true)
      setIsMicMuted(false)
    } catch (e: any) {
      console.error('Failed to connect:', e)
      setConnectionState('disconnected')
      setVoiceState('ERROR')
      alert(`Connection failed: ${e.message || e}`)
    }
  }

  const handleDisconnect = async () => {
    if (roomRef.current) {
      await roomRef.current.disconnect()
      roomRef.current = null
    }
    setConnectionState('disconnected')
    setVoiceState('DISCONNECTED')
    setActiveTool(null)
  }

  const handleToggleMic = async () => {
    if (!roomRef.current || connectionState !== 'connected') return
    const nextState = !isMicMuted
    await roomRef.current.localParticipant.setMicrophoneEnabled(!nextState)
    setIsMicMuted(nextState)
  }

  const getVoiceStateBadge = (state: string) => {
    switch (state) {
      case 'SPEAKING':
        return { color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50', label: 'Speaking', ring: 'border-emerald-400' }
      case 'THINKING':
        return { color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/50', label: 'Thinking', ring: 'border-cyan-400' }
      case 'TOOL_EXECUTING':
        return { color: 'bg-purple-500/20 text-purple-400 border-purple-500/50', label: 'Executing Tool', ring: 'border-purple-400' }
      case 'LISTENING':
        return { color: 'bg-blue-500/20 text-blue-400 border-blue-500/50', label: 'Listening', ring: 'border-blue-400' }
      case 'INTERRUPTED':
        return { color: 'bg-amber-500/20 text-amber-400 border-amber-500/50', label: 'Interrupted', ring: 'border-amber-400' }
      case 'ERROR':
        return { color: 'bg-rose-500/20 text-rose-400 border-rose-500/50', label: 'Error', ring: 'border-rose-400' }
      default:
        return { color: 'bg-slate-700/30 text-slate-400 border-slate-700', label: 'Idle', ring: 'border-slate-600' }
    }
  }

  const getWorkflowBadge = (state: string) => {
    switch (state) {
      case 'AWAITING_BOOKING_CONFIRMATION':
        return {
          color: '#f59e0b',
          bg: 'rgba(245, 158, 11, 0.15)',
          border: 'rgba(245, 158, 11, 0.4)',
          label: 'Awaiting Confirmation',
        }
      case 'BOOKED':
        return {
          color: '#10b981',
          bg: 'rgba(16, 185, 129, 0.15)',
          border: 'rgba(16, 185, 129, 0.4)',
          label: 'Showing Booked',
        }
      case 'PROPERTY_SELECTED':
        return {
          color: '#38bdf8',
          bg: 'rgba(56, 189, 248, 0.15)',
          border: 'rgba(56, 189, 248, 0.4)',
          label: 'Property Selected',
        }
      case 'CHECKING_AVAILABILITY':
        return {
          color: '#818cf8',
          bg: 'rgba(129, 140, 248, 0.15)',
          border: 'rgba(129, 140, 248, 0.4)',
          label: 'Checking Calendar',
        }
      case 'SHOWING_SELECTED':
        return {
          color: '#c084fc',
          bg: 'rgba(192, 132, 252, 0.15)',
          border: 'rgba(192, 132, 252, 0.4)',
          label: 'Slot Selected',
        }
      case 'REVIEWING_RESULTS':
        return {
          color: '#06b6d4',
          bg: 'rgba(6, 182, 212, 0.15)',
          border: 'rgba(6, 182, 212, 0.4)',
          label: 'Reviewing Results',
        }
      case 'SEARCHING':
        return {
          color: '#38bdf8',
          bg: 'rgba(56, 189, 248, 0.15)',
          border: 'rgba(56, 189, 248, 0.4)',
          label: 'Searching Listings',
        }
      default:
        return {
          color: '#94a3b8',
          bg: 'rgba(148, 163, 184, 0.1)',
          border: 'rgba(148, 163, 184, 0.2)',
          label: 'Idle / Discovery',
        }
    }
  }

  const badge = getVoiceStateBadge(voiceState)
  const wfBadge = getWorkflowBadge(workflowState)

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '24px' }}>
      {/* Top Navbar */}
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          paddingBottom: '20px',
          borderBottom: '1px solid var(--border)',
          marginBottom: '24px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #0284c7, #38bdf8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
            }}
          >
            <Radio size={22} />
          </div>
          <div>
            <h1 style={{ fontSize: '20px', fontWeight: '700', color: '#f8fafc', margin: 0 }}>
              PropRelay
            </h1>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0 }}>
              Real-Time Residential Voice AI • 100% Local $0 Mode
            </p>
          </div>
        </div>

        {/* Local Services Status */}
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            <div
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: health.livekit ? '#10b981' : '#f43f5e',
              }}
            />
            <span style={{ color: 'var(--text-muted)' }}>LiveKit (7880)</span>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            <div
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: health.ollama ? '#10b981' : '#f43f5e',
              }}
            />
            <span style={{ color: 'var(--text-muted)' }}>Ollama (Qwen 7B)</span>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            <div
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: health.kokoro ? '#10b981' : '#f43f5e',
              }}
            />
            <span style={{ color: 'var(--text-muted)' }}>Kokoro (8880)</span>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '20px',
          borderBottom: '1px solid var(--border)',
          paddingBottom: '12px',
        }}
      >
        <button
          onClick={() => setActiveTab('live')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: '8px',
            border: activeTab === 'live' ? '1px solid #0284c7' : '1px solid transparent',
            background: activeTab === 'live' ? 'rgba(2, 132, 199, 0.15)' : 'transparent',
            color: activeTab === 'live' ? '#38bdf8' : 'var(--text-muted)',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
          }}
        >
          <Radio size={16} />
          Live Session
        </button>

        <button
          onClick={() => setActiveTab('observability')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: '8px',
            border: activeTab === 'observability' ? '1px solid #0284c7' : '1px solid transparent',
            background: activeTab === 'observability' ? 'rgba(2, 132, 199, 0.15)' : 'transparent',
            color: activeTab === 'observability' ? '#38bdf8' : 'var(--text-muted)',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
          }}
        >
          <Activity size={16} />
          Latency Waterfall & Workflow Inspector
          {structuredErrors.length > 0 && (
            <span
              style={{
                background: '#f43f5e',
                color: '#fff',
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '10px',
              }}
            >
              {structuredErrors.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('replay')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: '8px',
            border: activeTab === 'replay' ? '1px solid #0284c7' : '1px solid transparent',
            background: activeTab === 'replay' ? 'rgba(2, 132, 199, 0.15)' : 'transparent',
            color: activeTab === 'replay' ? '#38bdf8' : 'var(--text-muted)',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
          }}
        >
          <History size={16} />
          Event Journal & Audit Log
        </button>
      </div>

      {/* Session Controls Bar */}
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '12px',
          padding: '16px 20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '24px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div>
            <label
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                color: 'var(--text-dim)',
                display: 'block',
                marginBottom: '4px',
              }}
            >
              Renter Name
            </label>
            <input
              type="text"
              value={userName}
              disabled={connectionState !== 'disconnected'}
              onChange={(e) => setUserName(e.target.value)}
              placeholder="Your name"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: '#fff',
                padding: '8px 12px',
                fontSize: '14px',
                width: '160px',
              }}
            />
          </div>

          <div style={{ marginLeft: '12px' }}>
            <span
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                color: 'var(--text-dim)',
                display: 'block',
                marginBottom: '6px',
              }}
            >
              Voice Status
            </span>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13px',
                padding: '4px 12px',
                borderRadius: '20px',
                border: '1px solid var(--border)',
                background: 'var(--bg-secondary)',
              }}
            >
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background:
                    voiceState === 'SPEAKING'
                      ? '#10b981'
                      : voiceState === 'LISTENING'
                      ? '#38bdf8'
                      : voiceState === 'THINKING'
                      ? '#06b6d4'
                      : voiceState === 'TOOL_EXECUTING'
                      ? '#a855f7'
                      : '#94a3b8',
                }}
              />
              <span style={{ fontWeight: '600' }}>{badge.label}</span>
              {activeTool && (
                <span style={{ color: '#c084fc', fontSize: '12px' }}>({activeTool})</span>
              )}
            </span>
          </div>

          <div style={{ marginLeft: '12px' }}>
            <span
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                color: 'var(--text-dim)',
                display: 'block',
                marginBottom: '6px',
              }}
            >
              Workflow State
            </span>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13px',
                padding: '4px 12px',
                borderRadius: '20px',
                border: `1px solid ${wfBadge.border}`,
                background: wfBadge.bg,
                color: wfBadge.color,
                fontWeight: '600',
              }}
            >
              <Compass size={14} />
              {wfBadge.label}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {connectionState === 'connected' && (
            <button
              onClick={handleToggleMic}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 16px',
                borderRadius: '8px',
                border: '1px solid var(--border)',
                background: isMicMuted ? '#f43f5e20' : 'var(--bg-secondary)',
                color: isMicMuted ? '#f43f5e' : '#e2e8f0',
                fontSize: '14px',
                fontWeight: '500',
              }}
            >
              {isMicMuted ? <MicOff size={18} /> : <Mic size={18} />}
              {isMicMuted ? 'Unmute' : 'Mute'}
            </button>
          )}

          {connectionState === 'disconnected' ? (
            <button
              onClick={handleConnect}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 20px',
                borderRadius: '8px',
                border: 'none',
                background: '#0284c7',
                color: '#fff',
                fontSize: '14px',
                fontWeight: '600',
              }}
            >
              <PhoneCall size={18} />
              Start Voice Call
            </button>
          ) : (
            <button
              onClick={handleDisconnect}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 20px',
                borderRadius: '8px',
                border: 'none',
                background: '#e11d48',
                color: '#fff',
                fontSize: '14px',
                fontWeight: '600',
              }}
            >
              <PhoneOff size={18} />
              End Session
            </button>
          )}
        </div>
      </div>

      {/* Pending Action Confirmation Safety Gate Banner */}
      {pendingAction && (
        <div
          style={{
            background:
              'linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(217, 119, 6, 0.08))',
            border: '1px solid rgba(245, 158, 11, 0.45)',
            borderRadius: '12px',
            padding: '16px 20px',
            marginBottom: '24px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '16px',
            boxShadow: '0 4px 20px -2px rgba(245, 158, 11, 0.15)',
          }}
        >
          <div
            style={{
              background: 'rgba(245, 158, 11, 0.2)',
              borderRadius: '8px',
              padding: '10px',
              color: '#f59e0b',
              marginTop: '2px',
            }}
          >
            <ShieldAlert size={24} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: '700',
                  textTransform: 'uppercase',
                  background: 'rgba(245, 158, 11, 0.25)',
                  color: '#fbbf24',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  letterSpacing: '0.5px',
                }}
              >
                {pendingAction.action_type.replace(/_/g, ' ')}
              </span>
              <span style={{ fontSize: '13px', fontWeight: '600', color: '#fef3c7' }}>
                Action Confirmation Required (Voice Safety Gate)
              </span>
            </div>
            <p
              style={{
                fontSize: '15px',
                fontWeight: '500',
                color: '#fff',
                margin: '0 0 6px 0',
                lineHeight: '1.4',
              }}
            >
              "{pendingAction.summary}"
            </p>
            <span style={{ fontSize: '12px', color: '#fcd34d' }}>
              Say <strong>"Yes, please"</strong> or <strong>"Confirm"</strong> to authorize, or{' '}
              <strong>"No, cancel"</strong> to decline.
            </span>
          </div>
        </div>
      )}

      {/* Main Split Grid */}
      {activeTab === 'live' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '24px' }}>
        {/* Left Column: Live Conversation Transcript */}
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: '12px',
            display: 'flex',
            flexDirection: 'column',
            height: '650px',
          }}
        >
          <div
            style={{
              padding: '16px 20px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Volume2 size={18} color="var(--accent-blue)" />
              <h2 style={{ fontSize: '15px', fontWeight: '600', color: '#f8fafc', margin: 0 }}>
                Live Conversation
              </h2>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
              {transcripts.length} turns recorded
            </span>
          </div>

          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            {transcripts.length === 0 ? (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  color: 'var(--text-dim)',
                  gap: '12px',
                }}
              >
                <Mic size={36} color="var(--border-focus)" />
                <p style={{ fontSize: '14px' }}>
                  {connectionState === 'connected'
                    ? 'Speak clearly into your microphone...'
                    : 'Click "Start Voice Call" to begin speaking with PropRelay'}
                </p>
              </div>
            ) : (
              transcripts.map((turn) => (
                <div
                  key={turn.id}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: turn.role === 'user' ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      fontSize: '11px',
                      color: 'var(--text-dim)',
                      marginBottom: '4px',
                    }}
                  >
                    <span>{turn.role === 'user' ? 'You' : 'PropRelay Agent'}</span>
                    <span>•</span>
                    <span>{turn.timestamp}</span>
                  </div>
                  <div
                    style={{
                      maxWidth: '85%',
                      padding: '12px 16px',
                      borderRadius: '12px',
                      fontSize: '14px',
                      lineHeight: '1.5',
                      background:
                        turn.role === 'user'
                          ? '#0284c7'
                          : 'var(--bg-secondary)',
                      color: turn.role === 'user' ? '#fff' : '#e2e8f0',
                      border:
                        turn.role === 'agent'
                          ? '1px solid var(--border)'
                          : 'none',
                    }}
                  >
                    {turn.text}
                  </div>
                </div>
              ))
            )}
            <div ref={transcriptEndRef} />
          </div>
        </div>

        {/* Right Column: Events & Latency Breakdown */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Active Property Card */}
          {activeProperty && (
            <div
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                borderRadius: '12px',
                padding: '14px 18px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '6px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Building2 size={18} color="var(--accent-cyan)" />
                  <h3 style={{ fontSize: '15px', fontWeight: '600', color: '#f8fafc', margin: 0 }}>
                    {activeProperty.title}
                  </h3>
                </div>
                <span
                  style={{
                    fontSize: '11px',
                    fontWeight: '600',
                    background: 'rgba(56, 189, 248, 0.15)',
                    color: '#38bdf8',
                    padding: '2px 8px',
                    borderRadius: '4px',
                  }}
                >
                  Active Focus
                </span>
              </div>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 10px 0' }}>
                {activeProperty.address}
                {activeProperty.neighborhood ? ` • ${activeProperty.neighborhood}` : ''}
              </p>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '12px' }}>
                {activeProperty.monthly_rent !== undefined && (
                  <span
                    style={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      color: '#10b981',
                      fontWeight: '600',
                    }}
                  >
                    ${activeProperty.monthly_rent.toLocaleString()}/mo
                  </span>
                )}
                {activeProperty.bedrooms !== undefined && (
                  <span
                    style={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      color: 'var(--text-muted)',
                    }}
                  >
                    {activeProperty.bedrooms} Bed{activeProperty.bedrooms === 1 ? '' : 's'}
                  </span>
                )}
                {activeProperty.bathrooms !== undefined && (
                  <span
                    style={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      color: 'var(--text-muted)',
                    }}
                  >
                    {activeProperty.bathrooms} Bath
                  </span>
                )}
                {activeProperty.square_feet !== undefined && (
                  <span
                    style={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      color: 'var(--text-muted)',
                    }}
                  >
                    {activeProperty.square_feet} sq ft
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Latency Breakdown Card */}
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              padding: '16px 20px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '16px',
              }}
            >
              <Clock size={18} color="var(--accent-cyan)" />
              <h2 style={{ fontSize: '15px', fontWeight: '600', color: '#f8fafc', margin: 0 }}>
                Live Turn Latency
              </h2>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
              <div
                style={{
                  background: 'var(--bg-secondary)',
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border)',
                }}
              >
                <span style={{ fontSize: '11px', color: 'var(--text-dim)', display: 'block' }}>
                  STT Whisper
                </span>
                <span style={{ fontSize: '18px', fontWeight: '700', color: '#38bdf8' }}>
                  {latency?.t_stt_ms ? `${latency.t_stt_ms}ms` : '--'}
                </span>
              </div>

              <div
                style={{
                  background: 'var(--bg-secondary)',
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border)',
                }}
              >
                <span style={{ fontSize: '11px', color: 'var(--text-dim)', display: 'block' }}>
                  LLM TTFT
                </span>
                <span style={{ fontSize: '18px', fontWeight: '700', color: '#06b6d4' }}>
                  {latency?.t_llm_ttft_ms ? `${latency.t_llm_ttft_ms}ms` : '--'}
                </span>
              </div>

              <div
                style={{
                  background: 'var(--bg-secondary)',
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border)',
                }}
              >
                <span style={{ fontSize: '11px', color: 'var(--text-dim)', display: 'block' }}>
                  TTS TTFB
                </span>
                <span style={{ fontSize: '18px', fontWeight: '700', color: '#10b981' }}>
                  {latency?.t_tts_ttfb_ms ? `${latency.t_tts_ttfb_ms}ms` : '--'}
                </span>
              </div>

              <div
                style={{
                  background: 'var(--bg-secondary)',
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border)',
                }}
              >
                <span style={{ fontSize: '11px', color: 'var(--text-dim)', display: 'block' }}>
                  Total Turn
                </span>
                <span style={{ fontSize: '18px', fontWeight: '700', color: '#c084fc' }}>
                  {latency?.t_total_reconstructed_ms
                    ? `${latency.t_total_reconstructed_ms}ms`
                    : '--'}
                </span>
              </div>
            </div>
          </div>

          {/* WebRTC Domain Events Feed */}
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              display: 'flex',
              flexDirection: 'column',
              height: '425px',
            }}
          >
            <div
              style={{
                padding: '14px 20px',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Zap size={18} color="var(--accent-purple)" />
                <h2 style={{ fontSize: '15px', fontWeight: '600', color: '#f8fafc', margin: 0 }}>
                  WebRTC Domain Events Stream
                </h2>
              </div>
              <span
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-dim)',
                }}
              >
                topic: proprelay.events
              </span>
            </div>

            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              {events.length === 0 ? (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '100%',
                    color: 'var(--text-dim)',
                    fontSize: '13px',
                  }}
                >
                  Waiting for domain events over data channel...
                </div>
              ) : (
                events.map((ev, i) => (
                  <div
                    key={`${ev.event_id}-${i}`}
                    style={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                      borderRadius: '6px',
                      padding: '10px 12px',
                      fontSize: '12px',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '4px',
                      }}
                    >
                      <span
                        style={{
                          fontWeight: '600',
                          color: ev.event_type.includes('error') || ev.event_type.includes('failed')
                            ? '#f43f5e'
                            : ev.event_type.includes('booked')
                            ? '#10b981'
                            : '#38bdf8',
                        }}
                      >
                        {ev.event_type}
                      </span>
                      <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                        {new Date(ev.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    {ev.payload && (
                      <pre
                        style={{
                          fontSize: '11px',
                          color: 'var(--text-muted)',
                          margin: 0,
                          overflowX: 'auto',
                        }}
                      >
                        {JSON.stringify(ev.payload, null, 2)}
                      </pre>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    )}

      {/* Observability & Latency Waterfall View */}
      {activeTab === 'observability' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Section 1: Turn Latency Waterfall Visualizer */}
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              padding: '20px 24px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Activity size={20} color="#38bdf8" />
                <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#f8fafc', margin: 0 }}>
                  Turn Latency Waterfall Visualizer
                </h2>
              </div>
              <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                Provenance: LiveKit Native + Local App Timers
              </span>
            </div>

            {latency && latency.t_total_reconstructed_ms ? (
              <div>
                {/* Horizontal Waterfall Bar */}
                {(() => {
                  const total = latency.t_total_reconstructed_ms || 1
                  const stt = latency.t_stt_ms || 0
                  const llm = latency.t_llm_ttft_ms || 0
                  const tts = latency.t_tts_ttfb_ms || 0
                  const tool = (latency as any).t_tool_ms || 0
                  const other = Math.max(0, total - (stt + llm + tts + tool))

                  const sttPct = Math.round((stt / total) * 100)
                  const llmPct = Math.round((llm / total) * 100)
                  const toolPct = Math.round((tool / total) * 100)
                  const ttsPct = Math.round((tts / total) * 100)
                  const otherPct = Math.max(0, 100 - (sttPct + llmPct + toolPct + ttsPct))

                  return (
                    <div>
                      <div
                        style={{
                          height: '32px',
                          display: 'flex',
                          borderRadius: '8px',
                          overflow: 'hidden',
                          border: '1px solid var(--border)',
                          marginBottom: '16px',
                        }}
                      >
                        <div
                          style={{
                            width: `${sttPct}%`,
                            background: '#38bdf8',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '11px',
                            fontWeight: '700',
                            color: '#0f172a',
                          }}
                          title={`STT: ${stt}ms (${sttPct}%)`}
                        >
                          {sttPct > 7 ? `STT ${stt}ms` : ''}
                        </div>
                        <div
                          style={{
                            width: `${llmPct}%`,
                            background: '#06b6d4',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '11px',
                            fontWeight: '700',
                            color: '#0f172a',
                          }}
                          title={`LLM TTFT: ${llm}ms (${llmPct}%)`}
                        >
                          {llmPct > 7 ? `LLM ${llm}ms` : ''}
                        </div>
                        {toolPct > 0 && (
                          <div
                            style={{
                              width: `${toolPct}%`,
                              background: '#a855f7',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '11px',
                              fontWeight: '700',
                              color: '#fff',
                            }}
                            title={`Tool: ${tool}ms (${toolPct}%)`}
                          >
                            {toolPct > 7 ? `Tool ${tool}ms` : ''}
                          </div>
                        )}
                        <div
                          style={{
                            width: `${ttsPct}%`,
                            background: '#10b981',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '11px',
                            fontWeight: '700',
                            color: '#0f172a',
                          }}
                          title={`TTS TTFB: ${tts}ms (${ttsPct}%)`}
                        >
                          {ttsPct > 7 ? `TTS ${tts}ms` : ''}
                        </div>
                        {otherPct > 0 && (
                          <div
                            style={{
                              width: `${otherPct}%`,
                              background: '#64748b',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '11px',
                              fontWeight: '700',
                              color: '#fff',
                            }}
                            title={`Overhead: ${other}ms (${otherPct}%)`}
                          >
                            {otherPct > 7 ? `Other` : ''}
                          </div>
                        )}
                      </div>

                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(5, 1fr)',
                          gap: '12px',
                        }}
                      >
                        <div
                          style={{
                            background: 'var(--bg-secondary)',
                            padding: '12px',
                            borderRadius: '8px',
                            border: '1px solid var(--border)',
                          }}
                        >
                          <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: '600' }}>
                            1. STT Whisper
                          </span>
                          <span
                            style={{
                              fontSize: '18px',
                              fontWeight: '700',
                              display: 'block',
                              color: '#fff',
                            }}
                          >
                            {stt}ms
                          </span>
                          <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                            Native Whisper timing
                          </span>
                        </div>
                        <div
                          style={{
                            background: 'var(--bg-secondary)',
                            padding: '12px',
                            borderRadius: '8px',
                            border: '1px solid var(--border)',
                          }}
                        >
                          <span style={{ fontSize: '11px', color: '#06b6d4', fontWeight: '600' }}>
                            2. LLM TTFT
                          </span>
                          <span
                            style={{
                              fontSize: '18px',
                              fontWeight: '700',
                              display: 'block',
                              color: '#fff',
                            }}
                          >
                            {llm}ms
                          </span>
                          <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                            Time-to-first-token
                          </span>
                        </div>
                        <div
                          style={{
                            background: 'var(--bg-secondary)',
                            padding: '12px',
                            borderRadius: '8px',
                            border: '1px solid var(--border)',
                          }}
                        >
                          <span style={{ fontSize: '11px', color: '#a855f7', fontWeight: '600' }}>
                            3. Tool Execution
                          </span>
                          <span
                            style={{
                              fontSize: '18px',
                              fontWeight: '700',
                              display: 'block',
                              color: '#fff',
                            }}
                          >
                            {tool ? `${tool}ms` : '0ms'}
                          </span>
                          <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                            Domain policy check
                          </span>
                        </div>
                        <div
                          style={{
                            background: 'var(--bg-secondary)',
                            padding: '12px',
                            borderRadius: '8px',
                            border: '1px solid var(--border)',
                          }}
                        >
                          <span style={{ fontSize: '11px', color: '#10b981', fontWeight: '600' }}>
                            4. TTS TTFB
                          </span>
                          <span
                            style={{
                              fontSize: '18px',
                              fontWeight: '700',
                              display: 'block',
                              color: '#fff',
                            }}
                          >
                            {tts}ms
                          </span>
                          <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                            First audio frame
                          </span>
                        </div>
                        <div
                          style={{
                            background: 'var(--bg-secondary)',
                            padding: '12px',
                            borderRadius: '8px',
                            border: '1px solid var(--border)',
                          }}
                        >
                          <span style={{ fontSize: '11px', color: '#c084fc', fontWeight: '600' }}>
                            5. Total Turn
                          </span>
                          <span
                            style={{
                              fontSize: '18px',
                              fontWeight: '700',
                              display: 'block',
                              color: '#c084fc',
                            }}
                          >
                            {total}ms
                          </span>
                          <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                            Reconstructed E2E
                          </span>
                        </div>
                      </div>
                    </div>
                  )
                })()}
              </div>
            ) : (
              <div
                style={{
                  textAlign: 'center',
                  padding: '24px',
                  color: 'var(--text-dim)',
                  fontSize: '13px',
                }}
              >
                No active turn metrics captured yet. Speak into the microphone during a voice call
                to observe live latency.
              </div>
            )}
          </div>

          {/* Section 2: Workflow Run Inspector */}
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              padding: '20px 24px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Compass size={20} color="#f59e0b" />
                <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#f8fafc', margin: 0 }}>
                  Workflow Run Inspector
                </h2>
              </div>
              <div
                style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}
              >
                <span style={{ color: 'var(--text-dim)' }}>Workflow ID:</span>
                <span
                  style={{ fontFamily: 'var(--font-mono)', color: '#38bdf8', fontWeight: '600' }}
                >
                  {activeWorkflowId || 'wf_idle'}
                </span>
              </div>
            </div>

            <div style={{ marginBottom: '12px' }}>
              <span
                style={{
                  fontSize: '12px',
                  color: 'var(--text-dim)',
                  display: 'block',
                  marginBottom: '8px',
                }}
              >
                State Machine Transition History:
              </span>
              <div
                style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}
              >
                {workflowTransitions.map((st, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '600',
                        background:
                          st === 'BOOKED'
                            ? 'rgba(16, 185, 129, 0.2)'
                            : st === 'AWAITING_BOOKING_CONFIRMATION'
                            ? 'rgba(245, 158, 11, 0.2)'
                            : 'var(--bg-secondary)',
                        color:
                          st === 'BOOKED'
                            ? '#10b981'
                            : st === 'AWAITING_BOOKING_CONFIRMATION'
                            ? '#f59e0b'
                            : '#94a3b8',
                        border: '1px solid var(--border)',
                      }}
                    >
                      {st}
                    </span>
                    {i < workflowTransitions.length - 1 && (
                      <span style={{ color: 'var(--text-dim)', fontSize: '12px' }}>→</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Section 3: Structured Errors & Reliability */}
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              padding: '20px 24px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <AlertCircle size={20} color="#f43f5e" />
                <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#f8fafc', margin: 0 }}>
                  Structured Error Taxonomy
                </h2>
              </div>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: '600',
                  padding: '2px 8px',
                  borderRadius: '10px',
                  background:
                    structuredErrors.length > 0 ? '#f43f5e20' : 'rgba(16, 185, 129, 0.2)',
                  color: structuredErrors.length > 0 ? '#f43f5e' : '#10b981',
                }}
              >
                {structuredErrors.length} Errors Caught
              </span>
            </div>

            {structuredErrors.length === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '24px',
                  color: 'var(--text-dim)',
                  fontSize: '13px',
                }}
              >
                Zero structured errors encountered in current session. Policy and speech pipelines
                operating normally.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {structuredErrors.map((err) => (
                  <div
                    key={err.error_id}
                    style={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid rgba(244, 63, 94, 0.3)',
                      borderRadius: '8px',
                      padding: '12px 16px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          marginBottom: '4px',
                        }}
                      >
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: '700',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: '#f43f5e',
                            color: '#fff',
                          }}
                        >
                          {err.code}
                        </span>
                        <span style={{ fontSize: '13px', fontWeight: '600', color: '#f8fafc' }}>
                          {err.message}
                        </span>
                      </div>
                      {err.workflow_id && (
                        <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                          Workflow: {err.workflow_id}
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                      {err.timestamp}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section 4: Global Metrics Summary */}
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              padding: '20px 24px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <BarChart3 size={20} color="#a855f7" />
                <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#f8fafc', margin: 0 }}>
                  Global Metrics Store Summary (/api/metrics/summary)
                </h2>
              </div>
              <button
                onClick={fetchMetricsSummary}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  color: 'var(--text-muted)',
                  fontSize: '12px',
                  padding: '6px 12px',
                  cursor: 'pointer',
                }}
              >
                <RefreshCw size={12} />
                Refresh
              </button>
            </div>

            {apiMetricsSummary ? (
              <div
                style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}
              >
                <div
                  style={{
                    background: 'var(--bg-secondary)',
                    padding: '12px',
                    borderRadius: '8px',
                    border: '1px solid var(--border)',
                  }}
                >
                  <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                    Total Recorded Sessions
                  </span>
                  <span
                    style={{
                      fontSize: '20px',
                      fontWeight: '700',
                      color: '#f8fafc',
                      display: 'block',
                    }}
                  >
                    {apiMetricsSummary.sample_counts?.total_sessions ?? 0}
                  </span>
                </div>
                <div
                  style={{
                    background: 'var(--bg-secondary)',
                    padding: '12px',
                    borderRadius: '8px',
                    border: '1px solid var(--border)',
                  }}
                >
                  <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                    Total Spoken Turns
                  </span>
                  <span
                    style={{
                      fontSize: '20px',
                      fontWeight: '700',
                      color: '#38bdf8',
                      display: 'block',
                    }}
                  >
                    {apiMetricsSummary.sample_counts?.total_turns ?? 0}
                  </span>
                </div>
                <div
                  style={{
                    background: 'var(--bg-secondary)',
                    padding: '12px',
                    borderRadius: '8px',
                    border: '1px solid var(--border)',
                  }}
                >
                  <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                    Workflow Completion Rate
                  </span>
                  <span
                    style={{
                      fontSize: '20px',
                      fontWeight: '700',
                      color: '#10b981',
                      display: 'block',
                    }}
                  >
                    {apiMetricsSummary.workflows?.completion_rate_pct !== undefined &&
                    apiMetricsSummary.workflows?.completion_rate_pct !== null
                      ? `${apiMetricsSummary.workflows.completion_rate_pct}%`
                      : 'N/A'}
                  </span>
                </div>
                <div
                  style={{
                    background: 'var(--bg-secondary)',
                    padding: '12px',
                    borderRadius: '8px',
                    border: '1px solid var(--border)',
                  }}
                >
                  <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                    Total Logged Errors
                  </span>
                  <span
                    style={{
                      fontSize: '20px',
                      fontWeight: '700',
                      color: '#f43f5e',
                      display: 'block',
                    }}
                  >
                    {apiMetricsSummary.sample_counts?.total_errors ?? 0}
                  </span>
                </div>
              </div>
            ) : (
              <div
                style={{
                  textAlign: 'center',
                  padding: '16px',
                  color: 'var(--text-dim)',
                  fontSize: '13px',
                }}
              >
                Loading local metrics store summary...
              </div>
            )}
          </div>
        </div>
      )}

      {/* Event Journal & Audit Log Replay View */}
      {activeTab === 'replay' && (
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: '12px',
            padding: '20px 24px',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '16px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <History size={20} color="#38bdf8" />
              <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#f8fafc', margin: 0 }}>
                Append-Only Event Journal (/api/events)
              </h2>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                type="text"
                value={replayFilter}
                onChange={(e) => setReplayFilter(e.target.value)}
                placeholder="Filter by event_type (e.g. showing.booked)"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  color: '#fff',
                  padding: '6px 12px',
                  fontSize: '12px',
                  width: '280px',
                }}
              />
              <button
                onClick={fetchReplayEvents}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: '#0284c7',
                  border: 'none',
                  borderRadius: '6px',
                  color: '#fff',
                  fontSize: '12px',
                  padding: '6px 14px',
                  cursor: 'pointer',
                  fontWeight: '600',
                }}
              >
                <RefreshCw size={12} />
                Fetch Events
              </button>
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              maxHeight: '600px',
              overflowY: 'auto',
            }}
          >
            {replayingEvents.length === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '32px',
                  color: 'var(--text-dim)',
                  fontSize: '13px',
                }}
              >
                No events found matching filter. Click "Fetch Events" to query the persistent
                journal.
              </div>
            ) : (
              replayingEvents.map((ev, i) => (
                <div
                  key={`${ev.event_id}-${i}`}
                  style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    padding: '12px 16px',
                    fontSize: '12px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '6px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-dim)',
                          fontSize: '11px',
                        }}
                      >
                        #{i + 1}
                      </span>
                      <span
                        style={{
                          fontWeight: '700',
                          color:
                            ev.event_type.includes('error') || ev.event_type.includes('failed')
                              ? '#f43f5e'
                              : ev.event_type.includes('booked')
                              ? '#10b981'
                              : '#38bdf8',
                        }}
                      >
                        {ev.event_type}
                      </span>
                      {(ev as any).workflow_id && (
                        <span
                          style={{
                            fontSize: '10px',
                            color: 'var(--text-dim)',
                            background: 'var(--bg-card)',
                            padding: '2px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          wf: {(ev as any).workflow_id}
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                      {new Date(ev.timestamp).toLocaleString()}
                    </span>
                  </div>
                  {ev.payload && (
                    <pre
                      style={{
                        margin: 0,
                        padding: '8px',
                        background: 'var(--bg-card)',
                        borderRadius: '4px',
                        fontSize: '11px',
                        color: 'var(--text-muted)',
                        overflowX: 'auto',
                      }}
                    >
                      {JSON.stringify(ev.payload, null, 2)}
                    </pre>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
