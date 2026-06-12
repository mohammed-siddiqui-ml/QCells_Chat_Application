export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  sources?: Source[]
}

export interface Source {
  title: string
  url: string
  type: 'confluence' | 'jira' | 'onboarding'
}

export interface User {
  id: string
  email: string
  isAdmin: boolean
}

export interface ChatRequest {
  message: string
  sessionId?: string
}

export interface ChatResponse {
  message: string
  sources?: Source[]
  sessionId: string
  needsClarification?: boolean
  clarificationQuestion?: string
}

export interface DataSource {
  id: string
  type: 'confluence' | 'jira' | 'onboarding'
  name: string
  config: Record<string, unknown>
  lastSync?: string
  status: 'active' | 'inactive' | 'error'
}
