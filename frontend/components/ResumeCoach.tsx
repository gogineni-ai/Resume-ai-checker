'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { chatWithCoach } from '../lib/api';

type CoachMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

type CoachPayloadMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

type CoachChatProps = {
  resumeContext?: string;
  jobContext?: string;
  initialPrompt?: string;
};

const DEFAULT_SUGGESTIONS = [
  'What skills am I missing?',
  'How can I strengthen my bullet points?',
  'What should I prioritize for this role?',
];

export default function ResumeCoach({ resumeContext = '', jobContext = '', initialPrompt = 'Hello! I\'ve scanned your resume details. Ask me anything about skill gaps, formatting improvements, or role alignment.' }: CoachChatProps) {
  const [messages, setMessages] = useState<CoachMessage[]>([
    { id: 'welcome', role: 'assistant', content: initialPrompt },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUserMessage, setLastUserMessage] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages, isLoading]);

  async function submitMessage(nextInput?: string) {
    const trimmed = (nextInput ?? input).trim();
    if (!trimmed || isLoading) return;

    const userMessage: CoachMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
    };

    const historyForRequest: CoachPayloadMessage[] = messages
      .filter((message) => message.id !== 'welcome')
      .map(({ role, content }) => ({ role, content }));

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLastUserMessage(trimmed);
    setError(null);
    setIsLoading(true);

    try {
      const payload: Parameters<typeof chatWithCoach>[0] = {
        messages: [
          ...historyForRequest,
          { role: 'user', content: trimmed } as CoachPayloadMessage,
        ],
        resume_context: resumeContext || undefined,
        job_context: jobContext || undefined,
      };

      const response = await chatWithCoach(payload);
      const reply = response?.reply || 'I could not generate a helpful response. Please try again.';

      setMessages((prev) => [
        ...prev,
        { id: `assistant-${Date.now()}`, role: 'assistant', content: reply },
      ]);
      setLastUserMessage(null);
    } catch (err: any) {
      setError(err?.message || 'The coach could not respond right now.');
    } finally {
      setIsLoading(false);
    }
  }

  function renderAssistantContent(content: string) {
    const lines = content.split('\n');
    const output: ReactNode[] = [];
    let listItems: ReactNode[] = [];

    lines.forEach((line, index) => {
      const trimmedLine = line.trim();
      if (!trimmedLine) {
        if (listItems.length) {
          output.push(
            <ul key={`list-${index}`} className="coachList">
              {listItems}
            </ul>,
          );
          listItems = [];
        }
        return;
      }

      if (/^[-*]\s+/.test(trimmedLine)) {
        listItems.push(
          <li key={`item-${index}`}>{trimmedLine.replace(/^[-*]\s+/, '')}</li>,
        );
        return;
      }

      if (listItems.length) {
        output.push(
          <ul key={`list-${index}`} className="coachList">
            {listItems}
          </ul>,
        );
        listItems = [];
      }

      output.push(
        <p key={`para-${index}`} className="coachParagraph">
          {trimmedLine}
        </p>,
      );
    });

    if (listItems.length) {
      output.push(
        <ul key="final-list" className="coachList">
          {listItems}
        </ul>,
      );
    }

    return <>{output}</>;
  }

  return (
    <section className="coachShell">
      <div className="coachHeader">
        <div>
          <h3>Resume Coach</h3>
          <p>Ask about gaps, metrics, wording, or role alignment.</p>
        </div>
      </div>

      <div className="coachSuggestions">
        {DEFAULT_SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className="coachChip"
            onClick={() => submitMessage(suggestion)}
            disabled={isLoading}
          >
            {suggestion}
          </button>
        ))}
      </div>

      <div ref={scrollRef} className="coachThread" aria-live="polite">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`coachRow ${message.role === 'user' ? 'coachRowUser' : 'coachRowAssistant'}`}
          >
            <div
              className={`coachBubble ${
                message.role === 'user' ? 'coachBubbleUser' : 'coachBubbleAssistant'
              }`}
            >
              {message.role === 'assistant' ? renderAssistantContent(message.content) : (
                <p className="coachParagraph">{message.content}</p>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="coachRow coachRowAssistant">
            <div className="coachBubble coachBubbleAssistant coachLoading">
              <span className="coachDot" />
              <span className="coachDot" />
              <span className="coachDot" />
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="coachErrorRow">
          <span>{error}</span>
          {lastUserMessage && (
            <button type="button" className="coachRetryButton" onClick={() => submitMessage(lastUserMessage)}>
              Retry
            </button>
          )}
        </div>
      )}

      <div className="coachComposer">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              submitMessage();
            }
          }}
          rows={3}
          disabled={isLoading}
          placeholder="Ask the coach about your resume, role fit, or interview prep..."
          className="coachInput"
        />
        <button type="button" className="primary" onClick={() => submitMessage()} disabled={isLoading || !input.trim()}>
          {isLoading ? 'Sending...' : 'Send'}
        </button>
      </div>
    </section>
  );
}
