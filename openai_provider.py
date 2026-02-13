"""
OpenAI LLM Provider for error analysis
"""

import os
import json
import time
from typing import Optional, Dict, Any
from openai import OpenAI
from types import NormalizedErrorLog, AnalysisResult


class OpenAILLMProvider:
    """OpenAI LLM provider for error analysis"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize OpenAI provider
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model name (defaults to OPENAI_MODEL env var or 'gpt-4')
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError('OPENAI_API_KEY environment variable is not set')
        
        self.model = model or os.getenv('OPENAI_MODEL', 'gpt-4')
        self.client = OpenAI(api_key=self.api_key)
        self.max_retries = 3
        self.retry_delay_ms = 1000
    
    def analyze_error(
        self,
        normalized_error: NormalizedErrorLog,
        repository_code: Optional[str] = None
    ) -> AnalysisResult:
        """
        Analyze error using OpenAI API
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(normalized_error, repository_code)
        
        try:
            response = self._call_openai([
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ])
            
            analysis = response.choices[0].message.content
            root_cause, suggested_fix, confidence_score = self._parse_analysis(analysis)
            
            return AnalysisResult(
                error_hash=normalized_error.error_hash,
                analysis=analysis,
                root_cause=root_cause,
                suggested_fix=suggested_fix,
                confidence_score=confidence_score,
                analyzed_at=int(time.time() * 1000),
                ttl=86400,
                expires_at=int((time.time() + 86400) * 1000),
            )
        except Exception as e:
            print(f'[OpenAI] Analysis failed: {e}')
            raise
    
    def _call_openai(self, messages: list) -> Any:
        """Call OpenAI API with retry logic"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000,
                )
                return response
            except Exception as e:
                last_error = e
                print(f'[OpenAI] Attempt {attempt + 1}/{self.max_retries} failed: {str(e)}')
                
                if attempt < self.max_retries - 1:
                    delay_ms = self.retry_delay_ms * (2 ** attempt)
                    time.sleep(delay_ms / 1000)
        
        raise last_error or Exception('OpenAI API call failed after retries')
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for error analysis"""
        return """You are an expert software engineer specializing in error diagnosis and debugging.
Your task is to analyze error logs and identify root causes, suggesting fixes.

Provide your analysis in the following JSON format:
{
  "rootCause": "Brief explanation of the root cause",
  "suggestedFix": "Concrete steps to fix the issue",
  "confidenceScore": 85,
  "analysis": "Detailed analysis of the error"
}

Be concise but thorough. Focus on actionable insights."""
    
    def _build_user_prompt(
        self,
        normalized_error: NormalizedErrorLog,
        repository_code: Optional[str] = None
    ) -> str:
        """Build user prompt with error details"""
        prompt = 'Analyze the following error:\n\n'
        prompt += f'Error Message: {normalized_error.error_message}\n'
        
        if normalized_error.error_code:
            prompt += f'Error Code: {normalized_error.error_code}\n'
        
        if normalized_error.file_path:
            prompt += f'File: {normalized_error.file_path}'
            if normalized_error.line_number:
                prompt += f':{normalized_error.line_number}'
            prompt += '\n'
        
        if normalized_error.stack_trace:
            prompt += f'Stack Trace:\n{normalized_error.stack_trace}\n'
        
        if normalized_error.context:
            try:
                context = json.loads(normalized_error.context)
                prompt += f'Context: {json.dumps(context, indent=2)}\n'
            except:
                prompt += f'Context: {normalized_error.context}\n'
        
        if repository_code:
            prompt += f'\nRelevant Code:\n{repository_code}\n'
        
        prompt += '\nProvide the analysis in JSON format.'
        
        return prompt
    
    def _parse_analysis(self, analysis: str) -> tuple[Optional[str], Optional[str], int]:
        """Parse analysis response from OpenAI"""
        try:
            # Try to extract JSON from response
            json_match = analysis.find('{')
            if json_match != -1:
                json_end = analysis.rfind('}') + 1
                json_str = analysis[json_match:json_end]
                parsed = json.loads(json_str)
                
                return (
                    parsed.get('rootCause'),
                    parsed.get('suggestedFix'),
                    parsed.get('confidenceScore', 75),
                )
        except Exception as e:
            print(f'[OpenAI] Failed to parse JSON response: {e}')
        
        # Fallback: extract key information from text
        root_cause = self._extract_section(analysis, 'root cause')
        suggested_fix = self._extract_section(analysis, 'suggested fix|solution|fix')
        
        return root_cause, suggested_fix, 60
    
    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """Extract section from text"""
        import re
        regex = rf'{section_name}[:\s]*([^\n]+)'
        match = re.search(regex, text, re.IGNORECASE)
        return match.group(1).strip() if match else None
