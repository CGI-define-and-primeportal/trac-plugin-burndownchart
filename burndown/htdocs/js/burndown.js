$(document).ready(function(){

  // Expects date as a string in yyyy-mm-dd format, with a time added for 
  // greater accuracy.
  window.addTime = function(date){
    var formatted_date = date + ' 12:01AM'
    return formatted_date
  };

  // Function which returns a two dimensional array. Each array has a 
  // date and value, with the value reflecting some kind of work either 
  // remaining or completed on that day
  window.dataSeries = function(curvedata){
    var series_data = [];
    for (var i=0; i < curvedata.length; i++) {
      series_data.push([addTime(curvedata[i][0]), curvedata[i][1]]);
    }
    return series_data;
  };

  // Curve data needed for jqPlot series
  var burndowncurve = dataSeries(burndowndata);  // Burndown Data
  var teameffortcurve = dataSeries(teameffortdata);  // Team Effort Data
  var idealcurve = dataSeries(idealcurvedata);  // Ideal Curve Data

  // Makes the jqPlot resize when the window dimensions change
  $(window).on('debouncedresize', function() {
        plot1.replot( { resetAxes: true } );
  });

  // Calculate the interval between x-axis dates (aka tickInterval)
  // 20 ticks is about right on a average sized screen
  // We plus one so that for 0.x numbers, we still get a 1 day interval
  tick_gap = Number(String((idealcurve.length / 20)));
  if (tick_gap < 1) {
    xaxis_interval = '1 day';
  }
  else {
    xaxis_interval = String(tick_gap + 1).split('.')[0] + ' days';
  }

  // Render the jqPlot burn down chart
  var plot1 = $.jqplot('chart1', [idealcurve, burndowncurve, teameffortcurve], {
    axesDefaults: {
      tickRenderer: $.jqplot.CanvasAxisTickRenderer,
      tickOptions: {
        fontFamily: 'Open Sans',
        fontSize: '8pt'
      },
      labelOptions: {
        textColor: '#0066CC',
        fontFamily: 'Open Sans',
        fontSize: '10pt',
        fontWeight: 'normal'
      }
    },
    axes: {
      xaxis: {
        renderer:$.jqplot.DateAxisRenderer,
        tickOptions:{formatString: '%d %b'},
        label: 'Days in Milestone',
        tickInterval:xaxis_interval,
        min: chartdata['start_date'],
        max: chartdata['end_date']
      },
      yaxis: {
        label: 'Effort (' + chartdata['effort_units'] +')',
        min: 0,
        labelRenderer: $.jqplot.CanvasAxisLabelRenderer
      }
    },
    highlighter: {
      show: true,
      tooltipAxes: 'both',
      sizeAdjust: 7.5,
      fadeTooltip: true,
      tooltipFadeSpeed: 'fast',
      tooltipAxes: 'xy',
      formatString: '%s - %s ' + chartdata['effort_units']
      },
    series:[
            {
              label: 'Ideal effort',
              color:'#AAA',
              showMarker: false,
              linePattern: 'dashed',
              lineWidth: 1.25,
              shadow: false
            },
            {
              color:'#23932C',
              label: 'Remaining effort',
              showMarker: false,
              shadow: false
            },
            {
              label:'Team effort',
              showMarker: false,
              color: '#FFD600',
              shadow: false
            },
           ],
    legend: {
      show: true
      }
  });

  // Makes the data points clickable, redirecting the user to the timeline
  $('#chart1').bind('jqplotDataClick',
      function (ev, seriesIndex, pointIndex, data, neighbor, gridData) {
        // data[0] is a unix timestamp
        var new_date = new Date(data[0]);
        // Necessary check as getDate does not always return two integers
        if (new_date.getDate() <= 9 ) {
          var date_string = new_date.getFullYear() + "-" + (new_date.getMonth() +1) + "-0" + new_date.getDate();
        }
        else if (new_date.getMonth() <= 8) { // Remember months are zero based in JS
          var date_string = new_date.getFullYear() + "-0" + (new_date.getMonth() +1) + "-" + new_date.getDate();
        }
        else {
          var date_string = new_date.getFullYear() + "-" + (new_date.getMonth() +1) + "-" + new_date.getDate();
        }
        // redirect to the timeline page for that date
        window.location = (chartdata['timeline_url'] + '&from=' + date_string)
      }
  );
});

