import Page from '@/components/page';

export default function Workflows() {
  return (
    <Page
      eyebrow="AUTOMATION"
      title="Processes"
      description="Native Agency OS business processes and durable execution history."
    >
      <div className="panel">
        <div className="empty">
          <strong>Native process orchestration is planned</strong>
          Business state, authorization and execution records will remain owned by the Agency OS.
          The current source includes execution and outbox foundations; dispatch, retries,
          reconciliation and process-level views still require implementation and validation.
        </div>
      </div>
    </Page>
  );
}
