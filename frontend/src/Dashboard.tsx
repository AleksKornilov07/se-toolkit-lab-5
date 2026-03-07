import { useState, useEffect } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Bar, Line } from 'react-chartjs-2';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend
);

// Types for API responses
interface ScoreBucket {
  bucket: string;
  count: number;
}

interface TimelinePoint {
  date: string;
  submissions: number;
}

interface PassRate {
  task: string;
  avg_score: number;
  attempts: number;
}

interface DashboardProps {
  apiBaseUrl: string;
}

const LABS = ['lab-01', 'lab-02', 'lab-03', 'lab-04', 'lab-05'];

const Dashboard: React.FC<DashboardProps> = ({ apiBaseUrl }) => {
  const [selectedLab, setSelectedLab] = useState<string>('lab-04');
  const [scores, setScores] = useState<ScoreBucket[]>([]);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [passRates, setPassRates] = useState<PassRate[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    const token = localStorage.getItem('api_token');
    if (!token) {
      setError('No API token found. Please connect first.');
      setLoading(false);
      return;
    }

    const headers = {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };

    try {
      // Fetch all data in parallel
      const [scoresRes, timelineRes, passRatesRes] = await Promise.all([
        fetch(`${apiBaseUrl}/analytics/scores?lab=${selectedLab}`, { headers }),
        fetch(`${apiBaseUrl}/analytics/timeline?lab=${selectedLab}`, { headers }),
        fetch(`${apiBaseUrl}/analytics/pass-rates?lab=${selectedLab}`, { headers }),
      ]);

      if (!scoresRes.ok) throw new Error(`Scores API: ${scoresRes.status}`);
      if (!timelineRes.ok) throw new Error(`Timeline API: ${timelineRes.status}`);
      if (!passRatesRes.ok) throw new Error(`Pass rates API: ${passRatesRes.status}`);

      const scoresData = await scoresRes.json();
      const timelineData = await timelineRes.json();
      const passRatesData = await passRatesRes.json();

      setScores(scoresData);
      setTimeline(timelineData);
      setPassRates(passRatesData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [selectedLab]);

  // Prepare chart data
  const barChartData = {
    labels: scores.map((item) => item.bucket),
    datasets: [
      {
        label: 'Number of submissions',
        data: scores.map((item) => item.count),
        backgroundColor: 'rgba(53, 162, 235, 0.5)',
        borderColor: 'rgb(53, 162, 235)',
        borderWidth: 1,
      },
    ],
  };

  const lineChartData = {
    labels: timeline.map((item) => item.date),
    datasets: [
      {
        label: 'Submissions per day',
        data: timeline.map((item) => item.submissions),
        borderColor: 'rgb(255, 99, 132)',
        backgroundColor: 'rgba(255, 99, 132, 0.5)',
        tension: 0.1,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
      },
    },
  };

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Analytics Dashboard</h1>
        <div className="lab-selector">
          <label htmlFor="lab-select">Select Lab: </label>
          <select
            id="lab-select"
            value={selectedLab}
            onChange={(e) => setSelectedLab(e.target.value)}
            disabled={loading}
          >
            {LABS.map((lab) => (
              <option key={lab} value={lab}>
                {lab.toUpperCase()}
              </option>
            ))}
          </select>
          <button onClick={fetchData} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {loading && <div className="loading">Loading...</div>}
      {error && <div className="error">Error: {error}</div>}

      {!loading && !error && (
        <>
          <div className="chart-container">
            <h2>Score Distribution</h2>
            <div className="chart-wrapper" style={{ height: '300px' }}>
              {scores.length > 0 ? (
                <Bar data={barChartData} options={chartOptions} />
              ) : (
                <p>No score data available</p>
              )}
            </div>
          </div>

          <div className="chart-container">
            <h2>Submissions Timeline</h2>
            <div className="chart-wrapper" style={{ height: '300px' }}>
              {timeline.length > 0 ? (
                <Line data={lineChartData} options={chartOptions} />
              ) : (
                <p>No timeline data available</p>
              )}
            </div>
          </div>

          <div className="table-container">
            <h2>Task Pass Rates</h2>
            {passRates.length > 0 ? (
              <table className="pass-rates-table">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Average Score (%)</th>
                    <th>Attempts</th>
                  </tr>
                </thead>
                <tbody>
                  {passRates.map((item, index) => (
                    <tr key={index}>
                      <td>{item.task}</td>
                      <td>{item.avg_score.toFixed(1)}%</td>
                      <td>{item.attempts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>No pass rate data available</p>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;
