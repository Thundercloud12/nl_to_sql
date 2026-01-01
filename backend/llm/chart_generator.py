# chart_generator.py
import plotly.graph_objects as go
import pandas as pd
from typing import Dict, Any
import json
import io


def generate_chart(sql_result: str, plan: dict, user_question: str) -> Dict[str, Any] | None:
    """
    Generate Plotly chart JSON from SQL result string.
    
    Args:
        sql_result: String representation of DataFrame (from interpreter)
        plan: Planner output with chart_type
        user_question: Original user question
    
    Returns:
        Plotly figure as JSON dict, or None if chart generation fails
    """
    try:
        # Parse SQL result string back to DataFrame
        df = parse_sql_result_to_df(sql_result)
        
        if df is None or df.empty:
            print("[CHART] No data to visualize")
            return None
        
        chart_type = plan.get("chart_type", "auto")
        
        # Auto-detect chart type if not specified
        if chart_type == "auto" or chart_type is None:
            chart_type = detect_chart_type(df, user_question)
        
        print(f"[CHART] Generating {chart_type} chart with {len(df)} rows")
        
        # Generate chart based on type
        if chart_type == "bar":
            fig = create_bar_chart(df)
        elif chart_type == "line":
            fig = create_line_chart(df)
        elif chart_type == "pie":
            fig = create_pie_chart(df)
        elif chart_type == "scatter":
            fig = create_scatter_chart(df)
        elif chart_type == "heatmap":
            fig = create_bar_chart(df)  # Fallback to bar for now
        else:
            fig = create_bar_chart(df)  # Default fallback
        
        # Return as JSON
        chart_json = json.loads(fig.to_json())
        print(f"[CHART] ✓ Chart generated successfully")
        return chart_json
    
    except Exception as e:
        print(f"[CHART] ✗ Error generating chart: {e}")
        return None


def parse_sql_result_to_df(sql_result: str) -> pd.DataFrame | None:
    """
    Parse SQL result string back to DataFrame.
    Uses pandas read_csv with fixed-width format to handle spaces in values.
    """
    try:
        # Use pandas to parse the string representation
        # This handles the aligned column format from DataFrame.to_string()
        from io import StringIO
        
        # Try reading as fixed-width format (handles spaces in values)
        df = pd.read_fwf(StringIO(sql_result), dtype=str)
        
        if df is None or df.empty:
            return None
        
        # Convert numeric columns
        for col in df.columns:
            try:
                # Try to convert to numeric, keeping NaN for non-numeric
                df[col] = pd.to_numeric(df[col], errors='ignore')
            except:
                pass
        
        print(f"[CHART] Parsed DataFrame: {len(df)} rows x {len(df.columns)} columns")
        print(f"[CHART] Columns: {list(df.columns)}")
        
        return df
    
    except Exception as e:
        print(f"[CHART] Error parsing SQL result: {e}")
        return None


def detect_chart_type(data: pd.DataFrame, question: str) -> str:
    """
    Use LLM to suggest best chart type based on data shape and question.
    Falls back to heuristics if LLM fails.
    """
    try:
        from utils.llm_utils import rate_limited_llm_call
        
        # Prepare data summary
        col_info = []
        for col in data.columns:
            dtype = "numeric" if pd.api.types.is_numeric_dtype(data[col]) else "categorical"
            col_info.append(f"{col} ({dtype})")
        
        sample_str = data.head(3).to_string(index=False)
        
        prompt = f"""
Given this data and question, suggest the BEST chart type.

Data columns: {', '.join(col_info)}
Data shape: {data.shape[0]} rows, {data.shape[1]} columns
Sample data:
{sample_str}

Question: {question}

Rules:
- Time series or dates → "line"
- Categorical comparison (bars side by side) → "bar"
- Part-to-whole (percentages/proportions) → "pie"
- Two numeric variables correlation → "scatter"
- Many categories (>10) → "bar"

Respond with ONLY ONE WORD: bar, line, pie, or scatter
"""
        
        response, _ = rate_limited_llm_call(prompt, model_name="gemini-2.0-flash-exp")
        chart_type = response.strip().lower()
        
        valid_types = ["bar", "line", "pie", "scatter"]
        if chart_type in valid_types:
            print(f"[CHART] LLM suggested: {chart_type}")
            return chart_type
        else:
            print(f"[CHART] LLM returned invalid type '{chart_type}', using heuristic")
            return detect_chart_type_heuristic(data)
    
    except Exception as e:
        print(f"[CHART] LLM detection failed: {e}, using heuristic")
        return detect_chart_type_heuristic(data)


def detect_chart_type_heuristic(data: pd.DataFrame) -> str:
    """
    Fallback heuristic for chart type detection.
    """
    if len(data.columns) < 2:
        return "bar"
    
    # Count numeric vs categorical columns
    numeric_cols = sum(1 for col in data.columns if pd.api.types.is_numeric_dtype(data[col]))
    
    # If 2+ numeric columns, use scatter
    if numeric_cols >= 2:
        return "scatter"
    
    # If 1 numeric column and few categories (<8), consider pie
    if numeric_cols == 1 and len(data) <= 7:
        return "pie"
    
    # Default to bar chart
    return "bar"


def create_bar_chart(data: pd.DataFrame) -> go.Figure:
    """Create bar chart from DataFrame"""
    if len(data.columns) < 2:
        raise ValueError("Need at least 2 columns for bar chart")
    
    # Assume first column is X (categorical), second is Y (numeric)
    x_col = data.columns[0]
    y_col = data.columns[1]
    
    # Limit to top 20 categories if too many
    if len(data) > 20:
        data = data.head(20)
        print(f"[CHART] Limited to top 20 rows for readability")
    
    fig = go.Figure(data=[
        go.Bar(
            x=data[x_col],
            y=data[y_col],
            marker=dict(
                color='#00e599',
                line=dict(color='#00b377', width=1)
            ),
            hovertemplate='<b>%{x}</b><br>%{y}<extra></extra>'
        )
    ])
    
    fig.update_layout(
        title=dict(
            text=f"{y_col} by {x_col}",
            font=dict(size=18, color='white')
        ),
        xaxis_title=x_col,
        yaxis_title=y_col,
        template="plotly_dark",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white', size=12),
        hoverlabel=dict(
            bgcolor="rgba(0,0,0,0.8)",
            font_size=13,
            font_color="white"
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig


def create_line_chart(data: pd.DataFrame) -> go.Figure:
    """Create line chart (for time series)"""
    if len(data.columns) < 2:
        raise ValueError("Need at least 2 columns for line chart")
    
    x_col = data.columns[0]
    y_col = data.columns[1]
    
    fig = go.Figure(data=[
        go.Scatter(
            x=data[x_col],
            y=data[y_col],
            mode='lines+markers',
            line=dict(color='#00e599', width=3),
            marker=dict(size=8, color='#00e599', line=dict(color='white', width=1)),
            hovertemplate='<b>%{x}</b><br>%{y}<extra></extra>'
        )
    ])
    
    fig.update_layout(
        title=dict(
            text=f"{y_col} over {x_col}",
            font=dict(size=18, color='white')
        ),
        xaxis_title=x_col,
        yaxis_title=y_col,
        template="plotly_dark",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white', size=12),
        hoverlabel=dict(
            bgcolor="rgba(0,0,0,0.8)",
            font_size=13,
            font_color="white"
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig


def create_pie_chart(data: pd.DataFrame) -> go.Figure:
    """Create pie chart"""
    if len(data.columns) < 2:
        raise ValueError("Need at least 2 columns for pie chart")
    
    labels_col = data.columns[0]
    values_col = data.columns[1]
    
    # Limit to top 10 slices
    if len(data) > 10:
        data = data.head(10)
        print(f"[CHART] Limited to top 10 slices for pie chart")
    
    colors = ['#00e599', '#00d088', '#00bb77', '#00a666', '#009155', '#007c44', '#006733', '#005222']
    
    fig = go.Figure(data=[
        go.Pie(
            labels=data[labels_col],
            values=data[values_col],
            marker=dict(
                colors=colors,
                line=dict(color='rgba(0,0,0,0.8)', width=2)
            ),
            hovertemplate='<b>%{label}</b><br>%{value}<br>%{percent}<extra></extra>',
            textposition='inside',
            textfont=dict(size=12, color='white')
        )
    ])
    
    fig.update_layout(
        title=dict(
            text=f"{values_col} by {labels_col}",
            font=dict(size=18, color='white')
        ),
        template="plotly_dark",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white', size=12),
        hoverlabel=dict(
            bgcolor="rgba(0,0,0,0.8)",
            font_size=13,
            font_color="white"
        ),
        margin=dict(l=60, r=60, t=60, b=60),
        showlegend=True,
        legend=dict(
            font=dict(color='white'),
            bgcolor='rgba(0,0,0,0.3)'
        )
    )
    
    return fig


def create_scatter_chart(data: pd.DataFrame) -> go.Figure:
    """Create scatter plot"""
    if len(data.columns) < 2:
        raise ValueError("Need at least 2 columns for scatter chart")
    
    x_col = data.columns[0]
    y_col = data.columns[1]
    
    fig = go.Figure(data=[
        go.Scatter(
            x=data[x_col],
            y=data[y_col],
            mode='markers',
            marker=dict(
                color='#00e599',
                size=10,
                line=dict(color='white', width=1),
                opacity=0.8
            ),
            hovertemplate='<b>X:</b> %{x}<br><b>Y:</b> %{y}<extra></extra>'
        )
    ])
    
    fig.update_layout(
        title=dict(
            text=f"{y_col} vs {x_col}",
            font=dict(size=18, color='white')
        ),
        xaxis_title=x_col,
        yaxis_title=y_col,
        template="plotly_dark",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white', size=12),
        hoverlabel=dict(
            bgcolor="rgba(0,0,0,0.8)",
            font_size=13,
            font_color="white"
        ),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    return fig
